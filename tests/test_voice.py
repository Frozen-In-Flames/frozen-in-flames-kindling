"""Tests for Part 8 (Voice characters), including the acceptance tests:
identity holds across performances, sufficiency flags inadequate references,
and revoked characters cannot render."""

import math

import numpy as np
import pytest

from kindling.assets import (
    VoiceCharacterStore,
    analyze_reference,
    create_voice_character,
    sufficiency_report,
)
from kindling.assets.voice import (
    UnsupportedPerformanceError,
    check_performance_supported,
    identity_similarity,
    render_with_character,
)
from kindling.vocals import ReferenceVocalRenderer
from kindling.vocals.alignment import align_lyric_line

RATE = 48000


def synth_reference(seconds=10.0):
    """Voice-like reference: five vowel segments (formant-filtered harmonic
    glides 150 to 300 Hz) with slow dynamics variation."""
    formants = {"IY": (270, 2290, 3010), "AE": (660, 1720, 2410),
                "AA": (730, 1090, 2440), "OW": (450, 1030, 2380),
                "UW": (300, 870, 2240)}
    seg_s = seconds / len(formants)
    out = []
    for v, (f1, f2, f3) in formants.items():
        n_seg = int(seg_s * RATE)
        t = np.arange(n_seg) / RATE
        f0 = 150.0 * (300.0 / 150.0) ** (t / seg_s)
        # Correct instantaneous phase for the exponential glide:
        # phase = 2*pi*h*integral(f0(t) dt).
        phase_base = (2 * math.pi * 150.0 * (seg_s / math.log(2.0))
                      * (2.0 ** (t / seg_s) - 1.0))
        sig = np.zeros(n_seg)
        for h in range(1, 9):
            freq = f0 * h
            env = (np.exp(-0.5 * ((freq - f1) / (f1 * 0.2)) ** 2)
                   + 0.6 * np.exp(-0.5 * ((freq - f2) / (f2 * 0.15)) ** 2)
                   + 0.3 * np.exp(-0.5 * ((freq - f3) / (f3 * 0.12)) ** 2))
            sig += np.sin(phase_base * h) / h * env
        amp = 0.55 + 0.4 * np.sin(2 * math.pi * 0.25 * t)
        out.append(sig * amp * 0.5)
    return np.concatenate(out).tolist()


@pytest.fixture
def ref_summary():
    return analyze_reference(synth_reference(), RATE, languages=["en"])


@pytest.fixture
def consent():
    return {"subject": "Test Singer", "recorded_at": "2026-10-17",
            "verified_against_audio": True, "verification_method": "reference-test",
            "rights_basis": "consent"}


def test_reference_analysis_finds_pitch_range(ref_summary):
    assert ref_summary["pitch_low_midi"] == pytest.approx(50.0, abs=2.0)  # 150 Hz
    assert ref_summary["pitch_high_midi"] == pytest.approx(62.0, abs=2.0)  # 300 Hz
    assert ref_summary["pitch_span_semitones"] > 10
    assert ref_summary["dynamics_db"]["range"] > 6.0
    assert ref_summary["voiced_s"] > 3.0
    assert ref_summary["vowel_count"] >= 4


def test_sufficiency_flags_inadequate_reference(ref_summary):
    report = sufficiency_report(ref_summary, {"pitch_low_midi": 40,
                                              "pitch_high_midi": 90})
    assert report["sufficient"] is False
    assert any("pitch range" in g for g in report["gaps"])
    assert report["options"]


def test_sufficiency_passes_supported_request(ref_summary):
    report = sufficiency_report(ref_summary, {"pitch_low_midi": 55,
                                              "pitch_high_midi": 64,
                                              "language": "en"})
    assert report["sufficient"] is True
    assert report["gaps"] == []


def test_sufficiency_flags_belt_without_dynamics(ref_summary):
    report = sufficiency_report(ref_summary, {"belt": 1.0})
    # The glide has dynamics range; belt alone is fine here. Force the gap:
    narrow = dict(ref_summary, dynamics_db={"p10": -20, "p90": -14, "range": 6.0})
    report2 = sufficiency_report(narrow, {"belt": 1.0})
    assert report2["sufficient"] is False
    assert any("belt" in g for g in report2["gaps"])


def test_create_requires_consent(ref_summary):
    with pytest.raises(ValueError):
        create_voice_character("NoConsent", ref_summary, None, {"id": "owner"})
    with pytest.raises(ValueError):
        create_voice_character("NoVerify", ref_summary,
                               {"subject": "X", "rights_basis": "consent"},
                               {"id": "owner"})


def test_create_with_licensed_rights(ref_summary):
    voice = create_voice_character("Licensed", ref_summary,
                                   {"rights_basis": "licensed",
                                    "license": "test fixture"},
                                   {"id": "owner"})
    assert voice["consent"]["rights_basis"] == "licensed"


def test_asset_has_all_spec_fields(ref_summary, consent):
    voice = create_voice_character("Mara", ref_summary, consent, {"id": "owner1"})
    for field in ("identity", "range_map", "timbre", "pronunciation",
                  "controls", "reference_summary", "version", "owner",
                  "consent", "provenance"):
        assert field in voice, field
    assert voice["range_map"]["registers"]
    assert voice["revoked"] is False


def _line():
    aligned = align_lyric_line("hello", [{"pitch": 60, "start_beats": 0.0,
                                          "duration_beats": 1.0},
                                         {"pitch": 62, "start_beats": 1.0,
                                          "duration_beats": 1.0}],
                               language="en")
    aligned["bpm"] = 120.0
    return aligned


def _stored_voice(ref_summary, consent, name="mara"):
    store = VoiceCharacterStore()
    voice = store.create(ref_summary, consent, name=name, owner={"id": "owner1"})
    return store, voice


def test_identity_survives_performance_change(ref_summary, consent):
    # Acceptance: changing the performance MUST NOT change identity.
    store, voice = _stored_voice(ref_summary, consent)
    renderer = ReferenceVocalRenderer()
    soft = render_with_character(store, voice["id"], _line(),
                                 {"dynamics": 0.3, "belt": 0.0}, seed=1,
                                 vocal_renderer=renderer)
    belt = render_with_character(store, voice["id"], _line(),
                                 {"dynamics": 1.0, "belt": 0.8}, seed=1,
                                 vocal_renderer=renderer)
    assert soft["metadata"]["identity_vector"] == belt["metadata"]["identity_vector"]
    assert soft["metadata"]["voice_id"] == belt["metadata"]["voice_id"]
    assert soft["metadata"]["voice_version"] == "v1"
    # ...but the audio differs: the performance changed.
    assert not np.array_equal(soft["audio"]["samples"], belt["audio"]["samples"])


def test_identity_similarity():
    v = [1.0, 2.0, 3.0]
    assert identity_similarity(v, v) == pytest.approx(1.0)
    assert identity_similarity(v, [3.0, 2.0, 1.0]) < 1.0


def test_unsupported_performance_raises_with_options(ref_summary, consent):
    store, voice = _stored_voice(ref_summary, consent)
    with pytest.raises(UnsupportedPerformanceError) as exc:
        render_with_character(store, voice["id"], _line(),
                              {"pitch_low_midi": 30, "pitch_high_midi": 95},
                              seed=1, vocal_renderer=ReferenceVocalRenderer())
    assert exc.value.gaps
    assert exc.value.options


def test_revoked_character_cannot_render(ref_summary, consent):
    store, voice = _stored_voice(ref_summary, consent)
    store.revoke(voice["id"])
    with pytest.raises(ValueError):
        render_with_character(store, voice["id"], _line(), {}, seed=1,
                              vocal_renderer=ReferenceVocalRenderer())


def test_render_marks_provenance_and_version(ref_summary, consent):
    store, voice = _stored_voice(ref_summary, consent)
    out = render_with_character(store, voice["id"], _line(), {}, seed=1,
                                vocal_renderer=ReferenceVocalRenderer())
    prov = out["audio"]["voice_provenance"]
    assert prov["voice_id"] == voice["id"]
    assert prov["voice_version"] == "v1"


def test_fork_and_share(ref_summary, consent):
    store, voice = _stored_voice(ref_summary, consent)
    child = store.fork(voice["id"], "mara_live")
    assert child["parent"] == voice["id"]
    assert child["version"] == "v1"
    assert child["id"] != voice["id"]
    shared = store.share(child["id"], {"share": "public-read"})
    assert shared["permissions"]["share"] == "public-read"


def test_store_component():
    store = VoiceCharacterStore()
    assert store.component_name == "Voice characters"
    assert "draft" in store.supported_tiers


def test_check_performance_supported_shape(ref_summary, consent):
    store, voice = _stored_voice(ref_summary, consent)
    report = store.sufficiency_report(voice["id"], {})
    assert report["supported"] is True
