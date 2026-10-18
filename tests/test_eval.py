"""Tests for Part 17: Evaluation program."""

import numpy as np
import pytest

from kindling.eval import (
    HUMAN_PROTOCOL, build_held_out, build_suite, check_audio_quality,
    check_edit_locality, check_release_gates, check_reproducibility_declared,
    check_tempo_key, datasheet, inter_rater_agreement, model_card,
    reliability_report, suite_ids, transfer_instrument_new_passages,
)


def _click_track(rate=22050, bpm=120.0, seconds=4.0):
    n = int(rate * seconds)
    sig = np.zeros(n)
    beat_n = int(rate * 60.0 / bpm)
    for b in range(0, n, beat_n):
        sig[b:b + 200] += np.hanning(200) * 0.9
    return sig


def test_suite_versioned_and_held_out():
    suite = build_suite()
    held = build_held_out()
    assert len(suite) >= 8 and len(held) >= 3
    ids = suite_ids(suite)
    assert len(set(ids)) == len(ids)
    # Held-out uses unusual combos not in the main suite.
    assert all("jazz" in p["genre"] or "metal" in p["genre"]
               or "ambient" in p["genre"] for p in held)


def test_tempo_check():
    sig = _click_track(bpm=120.0)
    result = check_tempo_key(sig, 22050, expected_bpm=120.0)
    assert result["passed"], result
    assert abs(result["detected_bpm"] - 120.0) < 12.0


def test_audio_quality_checks():
    rate = 22050
    sig = np.sin(2 * np.pi * 440 * np.arange(rate) / rate) * 0.5
    stereo = np.stack([sig, sig])
    result = check_audio_quality(stereo, rate)
    assert result["passed"], result["checks"]
    clipped = np.ones((2, rate))
    assert check_audio_quality(clipped, rate)["passed"] is False


def test_edit_locality_check():
    rate = 22050
    n = rate * 4
    rng = np.random.default_rng(0)
    before = rng.standard_normal(n) * 0.1
    after = before.copy()
    after[int(rate):int(2 * rate)] += 0.3  # edit 1-2 s
    mask = np.zeros(n, dtype=bool)
    mask[int(rate):int(2 * rate)] = True
    result = check_edit_locality(before, after, mask, rate)
    assert result["passed"], result


def test_reliability_report():
    def render(seed):
        rng = np.random.default_rng(seed)
        return rng.standard_normal(22050) * 0.1
    def check(audio):
        return float(np.max(np.abs(audio))) < 1.0
    report = reliability_report(render, check, seeds=[1, 2, 3, 4])
    assert report["pass_rate"] == 1.0
    assert report["severe_failure_rate"] == 0.0


def test_inter_rater_agreement():
    # Two raters agreeing closely.
    ratings = [[4, 5, 3, 4], [4, 5, 4, 4]]
    assert inter_rater_agreement(ratings) >= 0.5
    assert HUMAN_PROTOCOL["blinding"]


def test_model_card_and_datasheet():
    card = model_card("guitar-student", "v1",
                      {"intended_use": "draft tier",
                       "limitations": "procedural reference"})
    assert card["kind"] == "model-card"
    sheet = datasheet("voice-refs", "v1", {"consent": "on file"})
    assert sheet["kind"] == "datasheet"


def test_release_gates():
    results = {g: {"passed": True} for g in
               ["quality", "vocals", "editing", "assets", "reliability",
                "reproducibility", "safety", "documentation"]}
    out = check_release_gates(results)
    assert out["release"] is True
    results["safety"] = {"passed": False}
    out = check_release_gates(results)
    assert out["release"] is False
    assert out["blocked_by"] == ["safety"]


def test_transfer_instrument():
    from kindling.instruments.distill import distill_guitar
    from kindling.instruments.synth import TeacherGuitar
    result = distill_guitar(rate=22050)
    passages = [
        ([{"midi": 55, "start_s": 0.0, "dur_s": 0.3, "vel": 0.8}],
         {"tone": 0.4, "attack": 0.5, "space": 0.1}),
    ]
    out = transfer_instrument_new_passages(result["student"],
                                           TeacherGuitar(), passages, 22050)
    assert out["passed"], out
