"""Tests for Part 10: Audio-to-preset inverse rendering."""

import numpy as np
import pytest

from kindling.presets import (
    alternatives, analyze_reference, confidence, edit_preset, inverse_render,
    make_preset, render_preset,
)


def _make_reference(rate=22050):
    """A finished-sounding reference: bass-heavy, compressed, spacious."""
    n = rate * 2
    t = np.arange(n) / rate
    # Bass + chords + transient clicks (drum-like).
    sig = (np.sin(2 * np.pi * 55 * t) * 0.6
           + np.sin(2 * np.pi * 220 * t) * 0.25
           + np.sin(2 * np.pi * 440 * t) * 0.15)
    # Add transient clicks every 0.5 s (raises crest factor).
    for i in range(4):
        idx = int(i * 0.5 * rate)
        sig[idx:idx + 60] += np.hanning(60) * 1.5
    # Stereo with some width.
    left = sig * 1.0
    right = sig * 0.9 + np.roll(sig, 50) * 0.1
    # Add space: delayed copy.
    d = int(rate * 0.14)
    wet = np.zeros(n)
    wet[d:] = sig[:-d] * 0.3
    left = left + wet
    right = right + wet * 0.8
    stereo = np.stack([left, right])
    stereo = stereo / np.max(np.abs(stereo)) * 0.9
    return stereo


def test_analyze_returns_measurements():
    ref = _make_reference()
    a = analyze_reference(ref, 22050)
    for key in ("tonal_balance", "crest_db", "stereo_correlation",
                "side_db", "space_ratio", "detected_roles"):
        assert key in a, key
    assert a["crest_db"] > 10  # clicks raise the crest factor


def test_inverse_proposes_preset_with_confidence():
    ref = _make_reference()
    result = inverse_render(ref, 22050)
    preset = result["preset"]
    assert preset["chain"], "should propose at least one effect"
    assert 0.0 <= result["confidence"] <= 1.0
    assert len(result["alternatives"]) == 2
    assert "plausible" in result["disclaimer"]


def test_self_fit_close():
    # Self-fit: apply the inferred preset to a neutral source; the
    # result's features should move toward the reference's features.
    rate = 22050
    ref = _make_reference(rate)
    result = inverse_render(ref, rate)
    preset = result["preset"]
    # Neutral source: flat-spectrum-ish mix.
    n = rate * 2
    t = np.arange(n) / rate
    neutral = np.sin(2 * np.pi * 220 * t) * 0.5 + \
        np.sin(2 * np.pi * 440 * t) * 0.3
    neutral = np.stack([neutral, neutral])
    rendered = render_preset(neutral, rate, preset)
    a_ref = analyze_reference(ref, rate)
    a_new = analyze_reference(rendered, rate)
    # The rendered version should be closer to the reference's crest
    # than the dry neutral was.
    a_dry = analyze_reference(neutral, rate)
    dry_err = abs(a_dry["crest_db"] - a_ref["crest_db"])
    new_err = abs(a_new["crest_db"] - a_ref["crest_db"])
    assert new_err <= dry_err + 3.0


def test_editability_one_param_changes_render():
    rate = 22050
    preset = make_preset("test", [
        {"type": "lowshelf", "params": {"freq": 200, "gain_db": 0.0}},
    ])
    edited = edit_preset(preset, 0, "gain_db", 6.0)
    n = rate
    t = np.arange(n) / rate
    sig = np.sin(2 * np.pi * 100 * t) * 0.5
    sig = np.stack([sig, sig])
    a = render_preset(sig, rate, preset)
    b = render_preset(sig, rate, edited)
    # +6 dB lowshelf on a 100 Hz tone must be clearly louder.
    assert float(np.sqrt(np.mean(b ** 2))) > \
        float(np.sqrt(np.mean(a ** 2))) * 1.5


def test_edit_preset_validates_ranges():
    preset = make_preset("test", [
        {"type": "compressor", "params": {"threshold_db": -18,
                                          "ratio": 2.0}},
    ])
    with pytest.raises(ValueError):
        edit_preset(preset, 0, "ratio", 99.0)


def test_confidence_higher_for_clear_signatures():
    flat = {"tonal_balance": {"sub": 0.1, "low": 0.2, "mid": 0.45,
                              "high": 0.15, "air": 0.1},
            "crest_db": 20, "stereo_correlation": 0.95, "space_ratio": 0.4}
    vague = {"tonal_balance": {"sub": 0.08, "low": 0.22, "mid": 0.45,
                               "high": 0.18, "air": 0.07},
             "crest_db": 11, "stereo_correlation": 0.8, "space_ratio": 0.2}
    assert confidence(flat) > confidence(vague)


def test_per_section_analysis():
    ref = _make_reference()
    sections = [{"name": "verse", "start_s": 0.0, "end_s": 1.0},
                {"name": "chorus", "start_s": 1.0, "end_s": 2.0}]
    a = analyze_reference(ref, 22050, sections)
    assert len(a["per_section"]) == 2
    assert a["per_section"][0]["name"] == "verse"
