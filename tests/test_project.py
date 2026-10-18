"""Tests for Part 15: Project state, versioning, reproducibility."""

import numpy as np
import pytest

from kindling.project import (ProjectBundle, check_reproducibility,
                              migrate_scene, pin_render_inputs)
from kindling.scene.model import make_scene


def test_bundle_round_trip(tmp_path):
    b = ProjectBundle("test-song")
    scene = make_scene()
    b.add_scene("v1", scene, parents=[])
    b.add_scene("v2", scene, parents=["v1"])
    b.pin_asset("voice:mara", "v1")
    b.set_seed("render", 42)
    b.render_settings = {"tier": "draft"}
    b.cache_audio("v1", "/tmp/audio.wav")
    b.snapshot_profile("artist1", {"version": 3})
    path = str(tmp_path / "bundle")
    b.save(path)
    assert b.verify_integrity(path)
    loaded = ProjectBundle.load(path)
    assert loaded.name == "test-song"
    assert loaded.version_graph["v2"] == ["v1"]
    assert loaded.pinned_assets["voice:mara"] == "v1"
    assert loaded.cached_audio["v1"] == "/tmp/audio.wav"


def test_pinning_records_hashes():
    pins = pin_render_inputs()
    for key in ("renderer", "mixer", "preset_engine", "tokenizer",
                "kindling_version"):
        assert key in pins, key
    assert len(pins["renderer"]) == 16


def test_reproducibility_levels():
    rate = 22050
    a = np.sin(2 * np.pi * 440 * np.arange(rate) / rate)
    # Bit-exact.
    r = check_reproducibility(a, a.copy(), rate)
    assert r["level"] == "A" and r["bit_exact"] is True
    # Perceptually equivalent (tiny noise).
    rng = np.random.default_rng(0)
    b = a + rng.standard_normal(len(a)) * 1e-4
    r = check_reproducibility(a, b, rate)
    assert r["level"] == "B", r
    # Clearly different.
    c = np.sin(2 * np.pi * 880 * np.arange(rate) / rate)
    r = check_reproducibility(a, c, rate)
    assert r["level"] is None


def test_migration_reports_lossy():
    old = {"schema_version": "1.0.0", "parts": [{"id": "p1"}],
           "lyrics": {"lines": [{"text": "hi"}]}}
    result = migrate_scene(old)
    assert result["schema_version"] == "3.0.0"
    assert result["migrations"] == ["1.0.0 -> 2.0.0", "2.0.0 -> 3.0.0"]
    # Lossy steps are reported (zero unreported loss).
    assert result["lossy"], "must report lossy steps"
    assert result["scene"]["parts"][0]["meta"]["source"] == "user"


def test_current_schema_no_migration():
    scene = make_scene()
    result = migrate_scene(scene)
    assert result["migrations"] == []
    assert result["lossy"] == []
