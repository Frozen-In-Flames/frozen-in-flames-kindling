"""Tests for Part 9: Virtual instruments."""

import numpy as np
import pytest

from kindling.instruments import (
    PerformanceEngine, distill_bass, distill_guitar, make_bass_asset,
    make_guitar_asset, make_keys_asset,
)
from kindling.instruments.synth import StudentGuitar, TeacherGuitar


def _part():
    return [
        {"midi": 48, "start_beats": 0.0, "duration_beats": 1.0, "vel": 0.8},
        {"midi": 52, "start_beats": 1.0, "duration_beats": 1.0, "vel": 0.7},
        {"midi": 55, "start_beats": 2.0, "duration_beats": 2.0, "vel": 0.9},
    ]


def _context(density=0.8):
    return {"tempo": 120.0, "density": density, "harmony": "C major",
            "neighbors": [{"role": "kick", "hits_beats": [0, 1, 2, 3]}]}


def test_asset_spec_validates():
    for asset in (make_guitar_asset(), make_bass_asset(), make_keys_asset()):
        assert asset.validate() == [], asset.name
        d = asset.to_dict()
        for field in ("pitch_range_midi", "articulations", "dynamics",
                      "timing", "phrasing", "sound_design", "context_inputs",
                      "version", "provenance"):
            assert field in d, field


def test_guitar_strummed_vs_fingerpicked():
    engine = PerformanceEngine()
    dense = engine.perform(_part(), _context(density=0.9),
                           "kindling-guitar", seed=1)
    sparse = engine.perform(_part(), _context(density=0.2),
                            "kindling-guitar", seed=1)
    assert all(n["articulation"] == "strummed" for n in dense)
    assert all(n["articulation"] == "fingerpicked" for n in sparse)


def test_bass_locks_with_kick():
    engine = PerformanceEngine()
    part = [{"midi": 36, "start_beats": 0.1, "duration_beats": 0.9,
             "vel": 0.8}]
    perf = engine.perform(part, _context(), "kindling-bass", seed=1)
    # 0.1 beats is within 0.25 of the kick at 0.0, so it locks.
    assert perf[0]["start_s"] == pytest.approx(0.0, abs=0.01)


def test_performance_is_deterministic():
    engine = PerformanceEngine()
    a = engine.perform(_part(), _context(), "kindling-guitar", seed=5)
    b = engine.perform(_part(), _context(), "kindling-guitar", seed=5)
    assert a == b


def test_teacher_renders_audio():
    teacher = TeacherGuitar()
    notes = [{"midi": 50, "start_s": 0.0, "dur_s": 0.5, "vel": 0.8}]
    sig = teacher.render(notes, {"tone": 0.5, "attack": 0.5, "space": 0.0},
                         22050, seed=1)
    assert len(sig) > 22050 * 0.5
    assert float(np.max(np.abs(sig))) > 0.1


def test_distillation_audit_passes():
    result = distill_guitar(rate=22050)
    audit = result["audit"]
    assert audit["passes"] is True, audit
    assert audit["control_monotonic"] is True
    assert audit["student_realtime_factor"] <= 1.0


def test_distilled_student_matches_teacher_on_unseen():
    result = distill_guitar(rate=22050)
    student = result["student"]
    teacher = TeacherGuitar()
    notes = [{"midi": 62, "start_s": 0.0, "dur_s": 0.4, "vel": 0.85},
             {"midi": 59, "start_s": 0.3, "dur_s": 0.4, "vel": 0.7}]
    controls = {"tone": 0.6, "attack": 0.4, "space": 0.15}
    t = teacher.render(notes, controls, 22050, seed=99)
    s = student.render(notes, controls, 22050, seed=99)
    # Student is quieter-simpler but must track the teacher's envelope.
    assert len(t) == len(s)
    assert float(np.corrcoef(np.abs(t), np.abs(s))[0, 1]) > 0.7


def test_bass_distillation_audit_passes():
    result = distill_bass(rate=22050)
    assert result["audit"]["passes"] is True, result["audit"]


def test_student_deterministic_across_song():
    student = StudentGuitar()
    notes = [{"midi": 50, "start_s": i * 0.5, "dur_s": 0.4, "vel": 0.8}
             for i in range(8)]
    a = student.render(notes, {"tone": 0.5}, 22050, seed=2)
    b = student.render(notes, {"tone": 0.5}, 22050, seed=2)
    assert np.array_equal(a, b)
