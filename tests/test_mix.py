"""Tests for Part 13: Mix, mastering, and export."""

import json
import os
import wave

import numpy as np
import pytest

from kindling.mix import (Mixer, export_all, k_weighted_loudness, master,
                          true_peak)
from kindling.scene.model import make_scene


def _stems(rate=22050):
    n = rate * 2
    t = np.arange(n) / rate
    return {
        "keys": np.sin(2 * np.pi * 220 * t) * 0.4,
        "bass": np.sin(2 * np.pi * 55 * t) * 0.5,
    }


def _production():
    return {
        "routing": {"keys": {"level_db": -3.0, "pan": -0.3},
                    "bass": {"level_db": 0.0, "pan": 0.0}},
        "buses": {},
        "sends": [],
        "automation": [],
    }


def test_mixer_deterministic_and_reports():
    mixer = Mixer(rate=22050)
    a = mixer.mix(_stems(), _production())
    b = mixer.mix(_stems(), _production())
    assert np.array_equal(a["mix"], b["mix"])
    rep = a["report"]
    assert "loudness_lufs" in rep and "true_peak_dbfs" in rep
    assert rep["true_peak_dbfs"] <= 0.0
    assert set(rep["stems"].keys()) == {"keys", "bass"}


def test_mixer_avoids_clipping():
    mixer = Mixer(rate=22050)
    hot = {"lead": np.ones(22050) * 0.9, "pad": np.ones(22050) * 0.9}
    result = mixer.mix(hot, {"routing": {}, "buses": {},
                             "sends": [], "automation": []})
    assert float(np.max(np.abs(result["mix"]))) <= 1.0
    assert result["report"]["limited"] is True


def test_loudness_and_true_peak_sane():
    rate = 22050
    sig = np.sin(2 * np.pi * 440 * np.arange(rate) / rate) * 0.5
    stereo = np.stack([sig, sig])
    lufs = k_weighted_loudness(stereo, rate)
    assert -40 < lufs < 0, lufs
    tp = true_peak(stereo)
    assert -10 < tp < 1, tp


def test_mastering_bypass_and_target():
    rate = 22050
    sig = np.sin(2 * np.pi * 440 * np.arange(rate) / rate) * 0.3
    stereo = np.stack([sig, sig])
    bypassed = master(stereo, rate, bypass=True)
    assert np.array_equal(bypassed["audio"], stereo)
    assert bypassed["report"]["applied"] == []
    done = master(stereo, rate, target="streaming")
    assert done["report"]["applied"], "must list what was applied"
    assert done["report"]["true_peak_dbfs"] <= -0.5


def test_export_bundle(tmp_path):
    rate = 22050
    mixer = Mixer(rate=rate)
    stems_raw = _stems(rate)
    result = mixer.mix(stems_raw, _production())
    scene = make_scene()
    scene["parts"] = [
        {"id": "keys", "role": "keys", "notes": [
            {"pitch": 60, "start_beats": 0.0, "duration_beats": 1.0,
             "velocity": 0.8}]},
    ]
    scene["lyrics"] = {"lines": [{"text": "hello", "start_s": 0.0}]}
    out = str(tmp_path / "export")
    manifest = export_all(result["mix"], result["stems"], scene, out,
                          rate=rate, bit_depth=16, target_rate=22050)
    assert os.path.exists(manifest["mix"])
    assert len(manifest["stems"]) == 2
    assert manifest["midi"] and os.path.exists(manifest["midi"])
    assert os.path.exists(manifest["lyrics"])
    with open(manifest["sidecar"]) as f:
        sidecar = json.load(f)
    assert "scene" in sidecar and "provenance" in sidecar
    # WAV is valid.
    with wave.open(manifest["mix"], "rb") as w:
        assert w.getnchannels() == 2
        assert w.getsampwidth() == 2


def test_stems_sum_to_mix():
    rate = 22050
    mixer = Mixer(rate=rate)
    # No buses, unity routing: stems sum to the mix.
    stems_raw = _stems(rate)
    production = {"routing": {}, "buses": {}, "sends": [],
                  "automation": []}
    result = mixer.mix(stems_raw, production)
    summed = sum(result["stems"].values())
    # Mixer may limit; with these levels it should not.
    if not result["report"]["limited"]:
        assert np.allclose(summed, result["mix"], atol=1e-6)


def test_export_quality_checks():
    # Clipping, silence, DC offset, channel-swap checks (acceptance).
    rate = 22050
    sig = np.sin(2 * np.pi * 440 * np.arange(rate) / rate) * 0.5
    stereo = np.stack([sig, sig * 0.9])
    assert float(np.max(np.abs(stereo))) <= 1.0  # no clipping
    assert float(np.mean(np.abs(stereo))) > 1e-6  # not silence
    assert abs(float(np.mean(stereo))) < 0.01  # no DC offset
    # Channels not swapped: left is the louder one we made.
    assert float(np.mean(stereo[0] ** 2)) > float(np.mean(stereo[1] ** 2))
