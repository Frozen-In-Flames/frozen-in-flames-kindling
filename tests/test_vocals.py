"""Tests for Part 7 (Vocals and lyrics), including the acceptance checks:
syllable-level alignment, line-level regeneration with unchanged neighbors,
expressive controls, and intelligibility reporting."""

import numpy as np
import pytest

from kindling.vocals import (
    SUPPORTED_LANGUAGES,
    ReferenceVocalRenderer,
    align_line,
    default_performance,
    phonemize,
    validate_performance,
    word_error_rate,
)
from kindling.vocals.alignment import align_lyric_line
from kindling.vocals.g2p import EnglishG2P, SpanishG2P
from kindling.vocals.intelligibility import (
    IntelligibilityReport,
    ReferenceIntelligibility,
    TranscriptionModel,
    wer_report,
)
from kindling.vocals.regen import regenerate_line
from kindling.scene.model import make_element_meta, make_scene


def flat(syllables):
    return [p for s in syllables for p in s["phonemes"]]


# ---------------------------------------------------------- G2P: English
def test_english_hello():
    syls = phonemize("hello", "en")
    assert len(syls) == 2
    assert syls[0]["phonemes"][:2] == ["HH", "EH"]
    assert syls[0]["stress"] == 1


def test_english_silent_e():
    assert flat(phonemize("make", "en")) == ["M", "EY", "K"]


def test_english_exception_the():
    assert flat(phonemize("the", "en")) == ["DH", "AH"]


def test_english_digraphs():
    phones = flat(phonemize("she", "en"))
    assert "SH" in phones
    assert "CH" in flat(phonemize("church", "en"))


def test_english_elision_exception():
    # "every" is two syllables, not three: the middle vowel elides.
    syls = phonemize("every", "en")
    assert len(syls) == 2


# ---------------------------------------------------------- G2P: Spanish
def test_spanish_hola():
    syls = phonemize("hola", "es")
    assert flat(syls) == ["O", "L", "A"]
    assert syls[0]["stress"] == 1  # llana: ends in a vowel


def test_spanish_accent_marks_stress():
    syls = phonemize("canción", "es")
    stressed = [s for s in syls if s["stress"] == 1]
    assert len(stressed) == 1
    assert "O" in stressed[0]["phonemes"]  # the accented ó
    assert "S" in flat(syls)  # c before i -> S


def test_spanish_aguda():
    syls = phonemize("corazón", "es")
    stressed = [s for s in syls if s["stress"] == 1]
    assert any("O" in s["phonemes"] for s in stressed)


def test_supported_languages_explicit():
    assert set(SUPPORTED_LANGUAGES) == {"en", "es"}
    assert isinstance(SUPPORTED_LANGUAGES["en"], EnglishG2P)
    assert isinstance(SUPPORTED_LANGUAGES["es"], SpanishG2P)


def test_unsupported_language_raises():
    with pytest.raises(ValueError):
        phonemize("bonjour", "fr")


# ---------------------------------------------------------- alignment
def _notes(n, start=0.0):
    return [{"pitch": 60 + i, "start_beats": start + i, "duration_beats": 0.9}
            for i in range(n)]


def test_align_equal_counts():
    syls = phonemize("hello world", "en")
    result = align_line(syls, _notes(len(syls)))
    assert all(a["status"] == "aligned" for a in result["alignment"])
    assert result["confidence"] == 1.0


def test_align_melisma():
    syls = phonemize("la", "en")
    result = align_line(syls, _notes(3))
    assert result["alignment"][0]["status"] == "melisma"
    assert len(result["alignment"][0]["notes"]) == 3


def test_align_unassigned_marked_not_dropped():
    syls = phonemize("hello beautiful world today", "en")
    assert len(syls) > 3
    result = align_line(syls, _notes(3))
    unassigned = [a for a in result["alignment"] if a["status"] == "unassigned"]
    assert len(unassigned) == len(syls) - 3
    assert result["warnings"]
    assert result["confidence"] < 1.0


def test_align_lyric_line_end_to_end():
    result = align_lyric_line("hello", _notes(2), language="en")
    assert result["language"] == "en"
    assert result["text"] == "hello"
    assert len(result["alignment"]) == 2


# ---------------------------------------------------------- controls
def test_controls_defaults_and_ranges():
    perf = default_performance()
    assert validate_performance({}) == perf
    assert validate_performance({"belt": 1.0})["belt"] == 1.0


def test_controls_reject_bad_values():
    with pytest.raises(ValueError):
        validate_performance({"belt": 2.0})
    with pytest.raises(ValueError):
        validate_performance({"timing_push_ms": 500})
    with pytest.raises(ValueError):
        validate_performance({"reverb": 0.5})


# ---------------------------------------------------------- renderer
def _line(text="hello", n_notes=2, language="en"):
    aligned = align_lyric_line(text, _notes(n_notes), language=language)
    aligned["bpm"] = 120.0
    return aligned


def test_vocal_render_deterministic():
    renderer = ReferenceVocalRenderer()
    line = _line()
    a = renderer.render_line("voice_x", line, {}, seed=42)
    b = renderer.render_line("voice_x", line, {}, seed=42)
    assert np.array_equal(a["audio"]["samples"], b["audio"]["samples"])
    assert a["audio"]["samples"].shape[1] == 2
    assert a["metadata"]["syllables_rendered"] == 2


def test_vocal_render_is_honest_about_itself():
    out = ReferenceVocalRenderer().render_line("voice_x", _line(), {}, seed=1)
    assert any("not an intelligible singing voice" in w
               for w in out["metadata"]["warnings"])


def test_expressive_controls_change_output():
    renderer = ReferenceVocalRenderer()
    line = _line()
    plain = renderer.render_line("v", line, {"vibrato_rate_hz": 0.0}, seed=1)
    vib = renderer.render_line("v", line, {"vibrato_rate_hz": 5.5}, seed=1)
    assert not np.array_equal(plain["audio"]["samples"], vib["audio"]["samples"])
    spoken = renderer.render_line("v", line, {"whisper": 1.0}, seed=1)
    sung = renderer.render_line("v", line, {"whisper": 0.0}, seed=1)
    assert not np.array_equal(spoken["audio"]["samples"], sung["audio"]["samples"])
    pushed = renderer.render_line("v", line, {"timing_push_ms": 60.0}, seed=1)
    assert not np.array_equal(pushed["audio"]["samples"], plain["audio"]["samples"])


def test_vocal_renderer_component():
    r = ReferenceVocalRenderer()
    assert r.component_name == "Vocal renderer"
    assert "draft" in r.supported_tiers


# ---------------------------------------------------------- line regen
def _regen_scene():
    scene = make_scene()
    scene["timeline"]["tempo"] = [{"bar": 1, "bpm": 120.0}]
    scene["lyrics"] = {"lines": [
        {"id": "ln_01", "text": "hello", "language": "en",
         "meta": make_element_meta(realization="symbolic")},
        {"id": "ln_02", "text": "world", "language": "en",
         "meta": make_element_meta(realization="symbolic")},
    ]}
    scene["vocals"] = [{
        "id": "vox_lead",
        "voice": {"id": "voice_x", "version": "v1"},
        "performance": {},
        "lines": ["ln_01", "ln_02"],
        "line_notes": {
            "ln_01": _notes(2, start=0.0),
            "ln_02": _notes(2, start=4.0),
        },
        "meta": make_element_meta(realization="intent"),
    }]
    return scene


def test_regenerate_line_changes_only_that_line():
    scene = _regen_scene()
    renderer = ReferenceVocalRenderer()
    before = regenerate_line(scene, "vox_lead", "ln_02", "world", renderer, seed=9)
    after = regenerate_line(scene, "vox_lead", "ln_02", "goodbye", renderer, seed=9)
    # The other line is untouched: re-rendering it gives identical audio.
    line1 = align_lyric_line("hello", _notes(2, start=0.0), language="en")
    line1["bpm"] = 120.0
    r1 = renderer.render_line("voice_x", line1, {}, seed=9)
    r1b = renderer.render_line("voice_x", line1, {}, seed=9)
    assert np.array_equal(r1["audio"]["samples"], r1b["audio"]["samples"])
    # The changed line renders differently.
    assert not np.array_equal(before["line_audio"]["samples"],
                              after["line_audio"]["samples"])
    # Scene carries the new text and alignment.
    new_scene = after["scene"]
    assert next(ln for ln in new_scene["lyrics"]["lines"]
                if ln["id"] == "ln_02")["text"] == "goodbye"
    assert "ln_02" in new_scene["vocals"][0]["line_alignments"]
    assert after["unchanged_lines"] == ["ln_01"]
    assert after["start_s"] < after["end_s"]


def test_regenerate_line_needs_notes():
    scene = _regen_scene()
    del scene["vocals"][0]["line_notes"]
    with pytest.raises(KeyError):
        regenerate_line(scene, "vox_lead", "ln_01", "hi",
                        ReferenceVocalRenderer(), seed=1)


# ---------------------------------------------------------- intelligibility
def test_wer_identical_is_zero():
    assert word_error_rate("hello world", "hello world") == 0.0


def test_wer_counts_errors():
    assert word_error_rate("a b c d", "a x c d") == pytest.approx(0.25)
    assert word_error_rate("a b", "a b c") == pytest.approx(0.5)


def test_wer_report_with_fake_asr():
    class EchoASR(TranscriptionModel):
        @property
        def model_id(self):
            return "test-echo"

        def transcribe(self, audio, sample_rate, language):
            return "hello world"

    audio = np.zeros((48000, 2))
    report = wer_report("hello world", EchoASR(), audio, 48000, "en")
    assert report["wer"] == 0.0
    assert report["passed"] is True
    assert report["method"] == "asr:test-echo"


def test_proxy_intelligibility_flags_silence():
    checker = ReferenceIntelligibility()
    silent = np.zeros((48000 * 2, 2))
    report = checker.check(silent, 48000, expected_syllables=4)
    assert report["flagged"] is True
    assert report["method"] == "proxy (no ASR model)"


def test_proxy_intelligibility_on_rendered_line():
    renderer = ReferenceVocalRenderer()
    out = renderer.render_line("v", _line("hello world", n_notes=4), {}, seed=1)
    checker = ReferenceIntelligibility()
    report = checker.check(out["audio"]["samples"], 48000, expected_syllables=4)
    assert report["detected_onsets"] >= 1
    assert "proxy" in report["method"]


def test_intelligibility_report_without_asr_is_honest():
    report = IntelligibilityReport().check_line(
        np.zeros((48000, 2)), 48000, "hello", expected_syllables=2)
    assert report["wer"]["status"] == "no-asr-model"
    assert "proxy" in report["proxy"]["method"]
