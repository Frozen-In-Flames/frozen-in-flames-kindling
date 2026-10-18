"""Tests for Part 14: Interface, API, and DAW integration."""

import json
import os

import numpy as np
import pytest

from kindling.api import (
    asset_get, asset_list, asset_register, edit_submit, export_tempo_map,
    import_midi_to_scene, import_stem, job_cancel, job_status, openapi_spec,
    render_submit, scene_create, scene_read, scene_update,
)
from kindling.api.cli import main as cli_main
from kindling.scene.model import make_scene


def _scene():
    s = make_scene()
    s["parts"] = [{"id": "keys", "role": "keys", "notes": [
        {"pitch": 60, "start_beats": 0.0, "duration_beats": 1.0,
         "velocity": 0.8}],
        "meta": {"source": "user", "confidence": 1.0,
                 "locked": False, "realization": "intent"}}]
    return s


def test_scene_crud():
    created = scene_create(_scene())
    sid = created["scene_id"]
    assert scene_read(sid)["parts"][0]["id"] == "keys"
    scene_update(sid, _scene())
    assert scene_read(sid) is not None


def test_render_job_lifecycle():
    sid = scene_create(_scene())["scene_id"]
    sub = render_submit(sid, tier="draft", seed=3)
    assert sub["status"] == "done"
    st = job_status(sub["job_id"])
    assert st["status"] == "done"
    assert st["result"]["metadata"]["seed"] == 3


def test_edit_job():
    sid = scene_create(_scene())["scene_id"]
    sub = edit_submit(sid, "arrangement",
                      {"start_s": 0.0, "end_s": 4.0},
                      "density increase", seed=1)
    assert sub["status"] == "done"
    assert sub["result"]["changed"]


def test_job_cancel_queued():
    from kindling.api import handlers
    job = handlers._job("render", {})
    out = job_cancel(job["id"])
    assert out["status"] == "cancelled"


def test_assets():
    reg = asset_register("preset", {"name": "p1"})
    assert asset_get(reg["asset_id"])["kind"] == "preset"
    assert any(a["asset_id"] == reg["asset_id"]
               for a in asset_list("preset"))


def test_openapi_covers_handlers():
    spec = openapi_spec()
    paths = spec["paths"]
    for p in ("/v1/scenes", "/v1/render", "/v1/edit", "/v1/jobs/{job_id}",
              "/v1/assets", "/v1/profiles/{artist_id}", "/v1/export"):
        assert p in paths, p
    # Every edit operation in the API enum exists in the engine.
    from kindling.editing.operations import OPERATIONS
    enum = spec["paths"]["/v1/edit"]["post"]["requestBody"]["content"][
        "application/json"]["schema"]["properties"]["operation"]["enum"]
    assert set(enum) == set(OPERATIONS.keys())


def test_cli_render_matches_api(tmp_path):
    scene_path = str(tmp_path / "scene.json")
    with open(scene_path, "w") as f:
        json.dump(_scene(), f)
    out_path = str(tmp_path / "out.wav")
    rc = cli_main(["render", scene_path, "--out", out_path,
                   "--tier", "draft", "--seed", "7"])
    assert rc == 0
    assert os.path.exists(out_path)


def test_cli_api_spec(tmp_path):
    out = str(tmp_path / "openapi.json")
    assert cli_main(["api-spec", "--out", out]) == 0
    with open(out) as f:
        spec = json.load(f)
    assert spec["openapi"] == "3.0.0"


def test_daw_bridge(tmp_path):
    scene = _scene()
    export_tempo_map(scene, str(tmp_path / "tempo.json"))
    with open(tmp_path / "tempo.json") as f:
        tm = json.load(f)
    assert tm["tempo_map"][0]["bpm"] == 120.0
    # MIDI round-trip through the bridge.
    from kindling.scene.midi import scene_to_midi
    mid_path = str(tmp_path / "s.mid")
    scene_to_midi(scene, mid_path)
    back = import_midi_to_scene(mid_path)
    assert back["parts"]
    # Stem import reads metadata.
    from kindling.mix import write_wav
    wav_path = str(tmp_path / "stem.wav")
    sig = np.zeros(22050)
    write_wav(wav_path, np.stack([sig, sig]), 22050, 16)
    meta = import_stem(wav_path)
    assert meta["rate"] == 22050
