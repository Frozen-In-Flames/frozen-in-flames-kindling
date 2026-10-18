"""Tests for Part 12: Editing engine."""

import numpy as np
import pytest

from kindling.editing import (
    DependencyGraph, EditRequest, Selection, TakeManager, crossfade_edits,
    edit_mask, outside_mask_distance, seam_score, verify_locked,
)
from kindling.editing.operations import OPERATIONS
from kindling.scene.model import make_scene


def _scene():
    s = make_scene()
    s["parts"] = [
        {"id": "piano", "role": "keys", "notes": [
            {"pitch": 60, "start_beats": float(i),
             "duration_beats": 0.9, "velocity": 0.8}
            for i in range(16)]},
        {"id": "bass", "role": "bass", "notes": [
            {"pitch": 36, "start_beats": float(i * 2),
             "duration_beats": 1.8, "velocity": 0.85}
            for i in range(8)]},
    ]
    s["sections"] = [
        {"id": "verse", "name": "verse", "bars": [0, 3]},
        {"id": "chorus", "name": "chorus", "bars": [4, 7]},
    ]
    s["lyrics"] = {"lines": [{"text": "hello"}, {"text": "world"}]}
    return s


def _req(op, **kw):
    sel = Selection(start_s=kw.pop("start_s", 2.0),
                    end_s=kw.pop("end_s", 4.0),
                    part_id=kw.pop("part_id", None),
                    element=kw.pop("element", None))
    return EditRequest(operation=op, scene_version_id="v1",
                       selection=sel,
                       instruction=kw.pop("instruction", "fill dense"),
                       seed=kw.pop("seed", 1),
                       lock_set=kw.pop("lock_set", []))


def test_all_operations_run():
    for op_name, fn in OPERATIONS.items():
        scene = _scene()
        req = _req(op_name, element="section:verse",
                   instruction="voice:new-voice v1")
        new_scene, changed = fn(scene, req)
        assert isinstance(new_scene, dict)
        assert isinstance(changed, list)


def test_inpaint_replaces_notes_in_range():
    scene = _scene()
    req = _req("inpaint", start_s=2.0, end_s=4.0, part_id="piano",
               instruction="fill sparse")
    new_scene, changed = OPERATIONS["inpaint"](scene, req)
    assert "part:piano" in changed
    piano = [p for p in new_scene["parts"] if p["id"] == "piano"][0]
    # Notes at beats 2,3 replaced; 0,1 and 4+ kept.
    starts = [n["start_beats"] for n in piano["notes"]]
    assert 0.0 in starts and 4.0 in starts


def test_continue_extends():
    scene = _scene()
    req = _req("continue", instruction="add 4 bars")
    new_scene, changed = OPERATIONS["continue"](scene, req)
    piano = [p for p in new_scene["parts"] if p["id"] == "piano"][0]
    assert max(n["start_beats"] for n in piano["notes"]) > 16.0


def test_lyric_edit_changes_only_line():
    scene = _scene()
    req = _req("lyric_edit", element="lyrics.line.1",
               instruction="goodbye")
    new_scene, changed = OPERATIONS["lyric_edit"](scene, req)
    assert new_scene["lyrics"]["lines"][1]["text"] == "goodbye"
    assert new_scene["lyrics"]["lines"][0]["text"] == "hello"
    assert changed == ["lyrics.line.1"]


def test_asset_swap():
    scene = _scene()
    req = _req("asset_swap", part_id="piano",
               instruction="instrument:kindling-guitar v1")
    new_scene, changed = OPERATIONS["asset_swap"](scene, req)
    piano = [p for p in new_scene["parts"] if p["id"] == "piano"][0]
    assert piano["instrument"] == "instrument:kindling-guitar v1"


def test_locality_outside_mask_small():
    rate = 22050
    n = rate * 8
    rng = np.random.default_rng(0)
    before = rng.standard_normal(n) * 0.1
    # Edit only 2-4 s: replace with something clearly different.
    edited = rng.standard_normal(int(rate * 2)) * 0.5 + 0.3
    after = crossfade_edits(before, edited, rate, 2.0, 4.0)
    mask = edit_mask(n, rate, 2.0, 4.0)
    dist = outside_mask_distance(before, after, mask, rate)
    # Outside the mask only the 10 ms crossfades differ.
    assert dist < 3.0, dist


def test_seam_score_detects_click():
    rate = 22050
    sig = np.zeros(rate * 2)
    sig[int(rate * 1.0)] = 1.0  # impulse click at the boundary
    score = seam_score(sig, rate, 1.0)
    assert score["click_db"] > -10


def test_verify_locked_bit_exact():
    a = np.zeros(1000)
    b = np.zeros(1000)
    result = verify_locked({"stem": a}, {"stem": b}, ["stem"])
    assert result["stem"] == "bit-exact"
    c = np.ones(1000) * 0.5
    with pytest.raises(ValueError):
        verify_locked({"stem": a}, {"stem": c}, ["stem"])


def test_dependency_graph_preview():
    g = DependencyGraph()
    g.build_from_scene(_scene())
    preview = g.preview(["part:piano"])
    assert "render:piano" in preview["nodes_to_rerender"]
    assert "render:bass" not in preview["nodes_to_rerender"]


def test_takes_and_comping():
    rate = 22050
    tm = TakeManager()
    for i in range(3):
        sig = np.sin(2 * np.pi * 440 * np.arange(rate) / rate) * (0.5 + i * 0.1)
        tm.add_take(f"take{i}", sig, rate, seed=i)
    assert tm.list_takes() == ["take0", "take1", "take2"]
    comped = tm.comp([
        {"take_id": "take0", "start_s": 0.0, "end_s": 0.5},
        {"take_id": "take2", "start_s": 0.5, "end_s": 1.0},
    ])
    assert len(comped) == rate
    # Second half is louder (take2).
    assert np.sqrt(np.mean(comped[rate // 2:] ** 2)) > \
        np.sqrt(np.mean(comped[:rate // 2] ** 2))
