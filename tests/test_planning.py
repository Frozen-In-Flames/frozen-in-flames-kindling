"""Tests for Part 6 (Song planning and rendering), including the acceptance
checks: tempo drift and key violations below threshold, lyric completeness,
and the bake-off harness."""

import numpy as np
import pytest

from kindling.planning.bakeoff import bake_off, baseline_bake_off
from kindling.planning import (
    HierarchicalRenderer,
    ReferenceInterpreter,
    ReferencePlanner,
    ReferenceRenderer,
    coherence_report,
    interpret,
)
from kindling.planning.planner import (
    arrangement_for,
    energy_curve_for,
    motif_for,
    progression_for,
)
from kindling.scene.model import make_element_meta, scene_to_seconds_map


def make_song(prompt="dark energetic 100 bpm verse chorus", lyrics="la\nna\nla\nna"):
    result = interpret(prompt, lyrics=lyrics)
    scene = result["scene"]
    # A drums part with quarter-note kicks so tempo is measurable.
    total_bars = max(s["bars"][1] for s in scene["sections"])
    notes = [{"pitch": 36, "start_beats": float(b), "duration_beats": 0.9,
              "velocity": 0.9} for b in range(total_bars * 4)]
    scene["parts"].append({
        "id": "part_drums", "role": "drums", "notes": notes,
        "meta": make_element_meta(source="user", confidence=1.0,
                                  realization="symbolic"),
    })
    return scene, result["assumptions"]


def test_interpret_extracts_tempo_key_sections():
    result = interpret("a dark ballad at 92 bpm in F# minor, verse then chorus")
    scene = result["scene"]
    assert scene["timeline"]["tempo"][0]["bpm"] == 92.0
    assert scene["timeline"]["key"][0]["key"] == "F# minor"
    assert [s["type"] for s in scene["sections"]] == ["verse", "chorus"]


def test_interpret_lists_assumptions():
    result = interpret("make me a song")
    assert any("assumed 120 BPM" in a for a in result["assumptions"])
    assert any("assumed C major" in a for a in result["assumptions"])
    assert any("assumed 4/4" in a for a in result["assumptions"])
    assert result["scene"]["sections"]


def test_interpret_attaches_lyrics():
    result = interpret("verse chorus", lyrics="hello\nworld")
    lines = result["scene"]["lyrics"]["lines"]
    assert [ln["text"] for ln in lines] == ["hello", "world"]
    assert result["scene"]["sections"][0]["lyrics"]


def test_interpreter_component():
    interp = ReferenceInterpreter()
    assert interp.component_name == "Prompt interpreter"
    assert "draft" in interp.supported_tiers
    out = interp.interpret("90 bpm chorus")
    assert out["scene"]["timeline"]["tempo"][0]["bpm"] == 90.0


def test_progression_is_functional():
    prog = progression_for("C major", "verse", 0)
    assert prog == ["C", "G", "Am", "F"]
    minor = progression_for("A minor", "chorus", 0)
    assert minor[0] == "Am"


def test_planner_fills_scene_and_respects_locks():
    scene, _ = make_song()
    scene["sections"][0]["meta"]["locked"] = True
    locked_energy = scene["sections"][0]["energy"]
    planner = ReferencePlanner()
    out = planner.plan(scene)
    planned = out["scene"]
    assert planned["harmony"]
    assert planned["motifs"]
    assert planned["arrangement"]
    assert out["changes"]
    # Locked section untouched.
    assert planned["sections"][0]["energy"] == locked_energy
    assert not any(planned["sections"][0]["id"] in c and "harmony" in c
                   for c in out["changes"])


def test_planner_alternatives():
    scene, _ = make_song()
    planner = ReferencePlanner()
    for element in ("harmony", "energy", "motif"):
        alts = planner.alternatives(scene, element, count=3)
        assert len(alts) == 3
        assert all(a["element"] == element for a in alts)
    with pytest.raises(ValueError):
        planner.alternatives(scene, "nope")


def test_arrangement_enters_exits():
    scene, _ = make_song()
    planner = ReferencePlanner()
    planned = planner.plan(scene)["scene"]
    chorus = [a for a in planned["arrangement"] if "chorus" in a["section"]][0]
    assert "pad" in chorus["roles"] or "guitar" in chorus["roles"]


def test_renderer_is_deterministic():
    scene, _ = make_song()
    renderer = ReferenceRenderer()
    a = renderer.render_fragment(scene, {}, seed=88123, tier="draft")
    b = renderer.render_fragment(scene, {}, seed=88123, tier="draft")
    assert np.array_equal(a["audio"]["samples"], b["audio"]["samples"])
    assert a["metadata"]["seed"] == 88123


def test_renderer_output_is_valid_stereo():
    scene, _ = make_song()
    out = ReferenceRenderer().render_fragment(scene, {}, seed=1, tier="draft")
    samples = out["audio"]["samples"]
    assert samples.ndim == 2 and samples.shape[1] == 2
    assert np.all(np.isfinite(samples))
    assert np.max(np.abs(samples)) <= 0.95 + 1e-9
    assert out["audio"]["sample_rate"] == 48000


def test_renderer_warns_on_vocal_guide():
    scene, _ = make_song()
    scene["vocals"].append({"id": "vox", "lines": ["ln_01"],
                            "meta": make_element_meta(realization="intent")})
    out = ReferenceRenderer().render_fragment(scene, {}, seed=1, tier="draft")
    assert any("Part 7" in w for w in out["metadata"]["warnings"])


def test_preview_tiers():
    scene, _ = make_song()
    renderer = ReferenceRenderer()
    sketch = renderer.render_preview(scene, {}, seed=5, preview="sketch")
    assert sketch["audio"]["sample_rate"] == 22050
    assert len(sketch["audio"]["samples"]) == int(8.0 * 22050)
    draft = renderer.render_preview(scene, {}, seed=5, preview="draft")
    assert draft["audio"]["sample_rate"] == 44100
    final = renderer.render_preview(scene, {}, seed=5, preview="final")
    assert final["audio"]["sample_rate"] == 48000


def test_sketch_predicts_final_change():
    # A change heard in the sketch shows up in the final too.
    scene, _ = make_song()
    renderer = ReferenceRenderer()
    before = renderer.render_preview(scene, {}, seed=5, preview="sketch")
    scene["parts"][0]["notes"].append(
        {"pitch": 60, "start_beats": 0.0, "duration_beats": 4.0, "velocity": 1.0})
    after = renderer.render_preview(scene, {}, seed=5, preview="sketch")
    assert not np.array_equal(before["audio"]["samples"], after["audio"]["samples"])
    f_before = ReferenceRenderer().render_preview(make_song()[0], {}, seed=5, preview="final")
    assert f_before["metadata"]["preview"] == "final"


def test_hierarchical_chunks_overlap_and_condition():
    scene, _ = make_song("verse chorus")
    total_bars = max(s["bars"][1] for s in scene["sections"])
    assert total_bars == 16
    renderer = HierarchicalRenderer(ReferenceRenderer(), chunk_bars=4, overlap_bars=1)
    out = renderer.render(scene, {}, seed=3, tier="draft")
    # starts at bars 1, 4, 7, 10, 13
    assert out["metadata"]["chunks"] == 5
    assert len(renderer.contexts_seen) == 5
    first, last = renderer.contexts_seen[0], renderer.contexts_seen[-1]
    assert first["prev_tail_audio"] is False
    assert first["next_scene"] is True
    assert last["next_scene"] is False
    assert last["prev_tail_audio"] is True
    samples = out["audio"]["samples"]
    assert np.all(np.isfinite(samples))
    expected_s = total_bars * 4 * 60.0 / scene["timeline"]["tempo"][0]["bpm"]
    assert len(samples) == pytest.approx(expected_s * 48000, rel=0.02)


def test_hierarchical_no_clicks_at_boundaries():
    scene, _ = make_song("verse chorus")
    renderer = HierarchicalRenderer(ReferenceRenderer(), chunk_bars=4, overlap_bars=1)
    out = renderer.render(scene, {}, seed=3, tier="draft")
    mono = np.asarray(out["audio"]["samples"])[:, 0]
    jumps = np.max(np.abs(np.diff(mono)))
    assert jumps < 0.5  # crossfaded joins, no hard clicks


def test_coherence_report_on_reference_render():
    scene, _ = make_song("100 bpm verse chorus", lyrics="la\nna")
    planned = ReferencePlanner().plan(scene)["scene"]
    # Melody follows the motif twice so motif return is checkable.
    motif = planned["motifs"][0]["intervals"]
    melody_notes = []
    for rep in range(2):
        for i, pitch in enumerate(motif):
            melody_notes.append({"pitch": int(pitch) + 12, "start_beats": float(rep * 8 + i),
                                 "duration_beats": 0.9, "velocity": 0.7})
    planned["melody"] = {"notes": melody_notes, "contour": None,
                         "meta": make_element_meta(realization="symbolic")}
    planned["vocals"] = [{"id": "vox_lead", "lines": ["ln_01", "ln_02"],
                          "meta": make_element_meta(realization="intent")}]
    rendered = ReferenceRenderer().render_fragment(planned, {}, seed=11, tier="draft")
    audio = rendered["audio"]["samples"]
    report = coherence_report(planned, audio, rendered["audio"]["sample_rate"])
    assert report["checks"]["lyric_completeness"]["passed"]
    assert report["checks"]["lyric_completeness"]["completeness"] == 1.0
    assert report["checks"]["motif_return"]["passed"]
    assert report["checks"]["tempo_drift"]["passed"], report["checks"]["tempo_drift"]


def test_bake_off_ranks_baseline():
    suite = [make_song("100 bpm verse")[0], make_song("90 bpm chorus")[0]]
    report = baseline_bake_off(suite, seed=0)
    assert report["winner"] == "reference-deterministic"
    assert report["candidates"][0]["deterministic"] is True
    assert report["candidates"][0]["valid"] is True


def test_bake_off_rejects_unknown_approach():
    with pytest.raises(ValueError):
        bake_off([{"name": "x", "approach": "telepathy", "renderer": None}], [])
