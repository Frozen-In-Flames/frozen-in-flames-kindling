"""Tests for Part 3 (The Musical Scene), including the acceptance tests:
MIDI round-trip with no note loss, saved-scene reproducibility, and
section-scoped diffs."""

import json
import math
import os
import struct
import wave

import pytest

from kindling.scene import (
    SCENE_SCHEMA,
    SceneStore,
    bar_to_seconds,
    make_element_meta,
    make_scene,
    scene_to_seconds_map,
    validate_scene,
)
from kindling.scene import midi as midi_io
from kindling.scene import musicxml_io
from kindling.scene import audio_import
from kindling.scene.schema import load_schema_file, write_schema_file
from kindling.scene.store import (
    asset_ref,
    diff_scenes,
    format_asset_ref,
    merge_scenes,
    parse_asset_ref,
    version_id_for,
)


def manual_example_scene():
    """The abridged example from Part 3.4."""
    scene = make_scene()
    scene["timeline"] = {
        "tempo": [{"bar": 1, "bpm": 92.0}],
        "meter": [{"bar": 1, "sig": "4/4"}],
        "key": [{"bar": 1, "key": "F# minor"}],
    }
    scene["sections"] = [
        {"id": "sec_verse1", "type": "verse", "bars": [9, 24], "energy": 0.35,
         "density": 0.5, "lyrics": ["ln_01", "ln_02", "ln_03", "ln_04"],
         "meta": make_element_meta(realization="symbolic")},
        {"id": "sec_chorus1", "type": "chorus", "bars": [25, 40], "energy": 0.8,
         "density": 0.7, "meta": make_element_meta(realization="symbolic")},
    ]
    scene["parts"] = [
        {"id": "part_bass", "role": "bass",
         "instrument": asset_ref("inst_sub_bass", "v3"),
         "notes": [{"pitch": 41, "start_beats": 0.0, "duration_beats": 1.0, "velocity": 0.9}],
         "meta": make_element_meta(realization="performance")},
    ]
    scene["vocals"] = [
        {"id": "vox_lead", "voice": asset_ref("voice_mara", "v2"),
         "performance": {"style": "close", "dynamics": "soft", "vibrato": "low"},
         "lines": ["ln_01"],
         "meta": make_element_meta(realization="intent")},
    ]
    scene["production"] = {"preset": asset_ref("preset_warm_tape", "v1"),
                           "routing": {}, "sends": [],
                           "meta": make_element_meta()}
    scene["render"] = {"sample_rate": 48000, "seed": 88123, "tier": "studio",
                       "model_versions": {}, "asset_versions": {}}
    return scene


def test_manual_example_validates():
    validate_scene(manual_example_scene())


def test_schema_file_matches_code():
    path = write_schema_file()
    assert load_schema_file(path) == SCENE_SCHEMA
    assert os.path.exists(path)


def test_bar_to_seconds_92bpm():
    scene = manual_example_scene()
    # bar 9 starts after 8 bars of 4 beats at 92 BPM
    expected = 8 * 4 * 60.0 / 92.0
    assert bar_to_seconds(scene, 9) == pytest.approx(expected)


def test_section_seconds_map():
    scene = manual_example_scene()
    smap = scene_to_seconds_map(scene)
    assert smap["sec_verse1"]["start_s"] == pytest.approx(8 * 4 * 60.0 / 92.0)
    assert smap["sec_verse1"]["end_s"] > smap["sec_verse1"]["start_s"]


def test_partially_realized_scene_is_valid():
    scene = make_scene()
    scene["sections"].append({
        "id": "sec_idea", "type": "chorus", "bars": [1, 8],
        "description": "bigger second chorus",
        "meta": make_element_meta(realization="intent", confidence=0.6),
    })
    validate_scene(scene)


def test_element_meta_rejects_bad_values():
    with pytest.raises(ValueError):
        make_element_meta(source="alien")
    with pytest.raises(ValueError):
        make_element_meta(realization="hologram")
    with pytest.raises(ValueError):
        make_element_meta(confidence=2.0)


def test_asset_ref_round_trip():
    ref = asset_ref("inst_sub_bass", "v3", sha256="abc123")
    assert format_asset_ref(ref) == "inst_sub_bass@v3"
    assert parse_asset_ref("voice_mara@v2") == {"id": "voice_mara", "version": "v2"}
    with pytest.raises(ValueError):
        parse_asset_ref("no-at-sign")


def test_store_save_load_is_deterministic():
    store = SceneStore()
    scene = manual_example_scene()
    vid1 = store.save_version(scene)
    vid2 = store.save_version(manual_example_scene())
    assert vid1 == vid2  # identical scenes, identical ids
    loaded = store.load_version(vid1)
    assert loaded["id"] == vid1
    assert loaded["sections"] == scene["sections"]


def test_store_versions_are_immutable():
    store = SceneStore()
    vid = store.save_version(manual_example_scene())
    loaded = store.load_version(vid)
    loaded["sections"].append({"id": "hack"})
    assert len(store.load_version(vid)["sections"]) == 2


def test_store_branch_and_history():
    store = SceneStore()
    v1 = store.save_version(manual_example_scene())
    store.branch(v1, "main")
    scene2 = store.load_version(v1)
    scene2["sections"][1]["energy"] = 0.9
    v2 = store.save_version(scene2, parent_id=v1)
    assert store.history(v2) == [v2, v1]
    assert store.branch_head("main") == v1


def test_diff_lists_only_edited_section():
    # Acceptance test: edit one section, diff lists only that section's elements.
    store = SceneStore()
    v1 = store.save_version(manual_example_scene())
    scene2 = store.load_version(v1)
    for section in scene2["sections"]:
        if section["id"] == "sec_chorus1":
            section["energy"] = 0.6
    v2 = store.save_version(scene2, parent_id=v1)
    lines = store.diff_versions(v1, v2)
    assert len(lines) == 1
    assert "sec_chorus1" in lines[0]
    assert "energy" in lines[0]
    assert "sec_verse1" not in lines[0]


def test_diff_human_readable_add_remove():
    old, new = manual_example_scene(), manual_example_scene()
    new["parts"].append({"id": "part_pad", "role": "pad",
                         "meta": make_element_meta()})
    lines = diff_scenes(old, new)
    assert any("added part" in line and "part_pad" in line for line in lines)
    assert any("role: pad" in line for line in lines)


def test_merge_no_conflict():
    store = SceneStore()
    v0 = store.save_version(manual_example_scene())
    a = store.load_version(v0)
    a["sections"][0]["energy"] = 0.5
    va = store.save_version(a, parent_id=v0)
    b = store.load_version(v0)
    b["sections"][1]["energy"] = 0.95
    vb = store.save_version(b, parent_id=v0)
    result = store.merge(va, vb)
    assert result["conflicts"] == []
    merged = store.load_version(result["merged_id"])
    energies = {s["id"]: s["energy"] for s in merged["sections"]}
    assert energies == {"sec_verse1": 0.5, "sec_chorus1": 0.95}


def test_merge_reports_conflict():
    store = SceneStore()
    v0 = store.save_version(manual_example_scene())
    a = store.load_version(v0)
    a["sections"][1]["energy"] = 0.5
    va = store.save_version(a, parent_id=v0)
    b = store.load_version(v0)
    b["sections"][1]["energy"] = 0.95
    vb = store.save_version(b, parent_id=v0)
    result = store.merge(va, vb)
    assert len(result["conflicts"]) == 1
    conflict = result["conflicts"][0]
    assert conflict["element"] == "sec_chorus1"
    assert conflict["field"] == "energy"
    assert conflict["ours"] == 0.5
    assert conflict["theirs"] == 0.95


def _note_key(note):
    return (note["pitch"], round(note["start_beats"], 6),
            round(note["duration_beats"], 6))


def test_midi_round_trip_no_note_loss(tmp_path):
    # Acceptance test: MIDI -> scene -> MIDI with no note loss.
    scene = manual_example_scene()
    scene["parts"][0]["notes"] = [
        {"pitch": 41, "start_beats": 0.0, "duration_beats": 1.0, "velocity": 0.9},
        {"pitch": 43, "start_beats": 1.0, "duration_beats": 0.5, "velocity": 0.7},
        {"pitch": 45, "start_beats": 2.0, "duration_beats": 2.0, "velocity": 0.8},
    ]
    path = str(tmp_path / "song.mid")
    midi_io.scene_to_midi(scene, path)
    parsed = midi_io.read_midi_file(path)
    assert parsed["ticks_per_quarter"] == midi_io.TPQ
    back = midi_io.midi_to_scene(parsed)
    validate_scene(back)
    original = {_note_key(n) for n in scene["parts"][0]["notes"]}
    round_tripped = set()
    for part in back["parts"]:
        round_tripped |= {_note_key(n) for n in part["notes"]}
    assert original == round_tripped


def test_midi_import_marks_source_and_confidence():
    parsed = {"format": 1, "ticks_per_quarter": 480, "tracks": [
        {"name": "piano", "notes": [
            {"pitch": 60, "start_tick": 0, "end_tick": 480,
             "velocity": 0.8, "channel": 0}],
         "tempo_changes": [(0, 100.0)], "sig_changes": [(0, (3, 4))]}]}
    scene = midi_io.midi_to_scene(parsed)
    validate_scene(scene)
    part = scene["parts"][0]
    assert part["meta"]["source"] == "imported"
    assert part["meta"]["confidence"] == 1.0
    assert part["meta"]["realization"] == "symbolic"
    assert scene["timeline"]["meter"][0]["sig"] == "3/4"


def test_musicxml_round_trip(tmp_path):
    scene = manual_example_scene()
    scene["parts"][0]["notes"] = [
        {"pitch": 60, "start_beats": 0.0, "duration_beats": 1.0, "velocity": 0.8},
        {"pitch": 62, "start_beats": 1.0, "duration_beats": 1.0, "velocity": 0.8},
        {"pitch": 64, "start_beats": 4.0, "duration_beats": 2.0, "velocity": 0.8},
    ]
    path = str(tmp_path / "song.musicxml")
    musicxml_io.scene_to_musicxml(scene, path)
    back = musicxml_io.musicxml_to_scene(path)
    validate_scene(back)
    original = {_note_key(n) for n in scene["parts"][0]["notes"]}
    round_tripped = {_note_key(n) for part in back["parts"] for n in part["notes"]}
    assert original == round_tripped


def _write_click_wav(path, bpm=120.0, seconds=8.0, rate=44100):
    clicks = int(seconds * rate)
    samples = [0.0] * clicks
    period = int(rate * 60.0 / bpm)
    for start in range(0, clicks, period):
        for i in range(min(200, clicks - start)):
            samples[start + i] += 0.9 * (1 - i / 200)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack(f"<{clicks}h",
                                   *[max(-32768, min(32767, int(s * 32767)))
                                     for s in samples]))


def test_audio_import_tempo_estimate(tmp_path):
    path = str(tmp_path / "click.wav")
    _write_click_wav(path, bpm=120.0)
    analysis = audio_import.analyze_audio(path)
    assert analysis["duration_s"] == pytest.approx(8.0, abs=0.01)
    assert analysis["tempo_estimate"]["bpm"] == pytest.approx(120.0, abs=3.0)
    assert analysis["tempo_estimate"]["confidence"] > 0.35


def test_audio_import_scene_is_honest(tmp_path):
    path = str(tmp_path / "click.wav")
    _write_click_wav(path, bpm=100.0)
    scene = audio_import.import_audio_as_scene(path, title="demo")
    validate_scene(scene)
    assert scene["melody"]["meta"]["realization"] == "audio"
    assert "warning" in scene["melody"]  # no invented structure


def test_stem_import(tmp_path):
    paths = []
    for i in range(2):
        path = str(tmp_path / f"stem{i}.wav")
        _write_click_wav(path, bpm=120.0, seconds=2.0)
        paths.append(path)
    scene = audio_import.import_stems_as_scene(paths)
    validate_scene(scene)
    assert len(scene["parts"]) == 2
    assert all(p["meta"]["realization"] == "audio" for p in scene["parts"])
