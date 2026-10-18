"""Reference vocal renderer (Part 7).

Renders one lyric line from aligned syllables with full expressive control.
The synthesis is formant-textured and prosody-faithful: vowels are harmonic
tones with vibrato, fricatives are shaped noise, stops are bursts, and every
expressive control audibly changes the output. What it is NOT is an
intelligible singing voice: true vocal synthesis needs a learned model,
which plugs into the VocalRenderer interface later. The metadata says this
plainly, and the intelligibility checker (intelligibility.py) will flag the
reference output, which is the system working as intended.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

import numpy as np

from kindling.interfaces import VocalRenderer as VocalRendererABC
from kindling.vocals.controls import validate_performance
from kindling.vocals.g2p import ARPABET_VOWELS

SAMPLE_RATE = 48000

_FRICATIVES = {"S", "Z", "SH", "ZH", "F", "V", "TH", "DH", "HH", "X"}
_STOPS = {"P", "B", "T", "D", "K", "G"}
_NASALS_LIQUIDS = {"M", "N", "NG", "L", "R", "W", "Y", "NY", "RR"}


def _midi_to_freq(pitch: int) -> float:
    return 440.0 * (2.0 ** ((pitch - 69) / 12.0))


def _vowel_tone(freq: float, dur_s: float, perf: Dict[str, Any],
                rng: np.random.RandomState) -> np.ndarray:
    n = max(16, int(dur_s * SAMPLE_RATE))
    t = np.arange(n) / SAMPLE_RATE
    rate_hz = perf["vibrato_rate_hz"]
    if rate_hz > 0:
        vib = np.sin(2 * math.pi * rate_hz * t) * (perf["vibrato_depth_cents"] / 1200.0)
    else:
        vib = np.zeros(n)
    phase = 2 * math.pi * np.cumsum(freq * (2.0 ** vib)) / SAMPLE_RATE
    brightness = 0.25 + 0.75 * perf["belt"]
    tone = sum(np.sin(phase * h) / (h ** (1.6 - brightness)) for h in range(1, 9))
    tone = tone / (np.max(np.abs(tone)) + 1e-9) * 0.8
    breath = rng.randn(n) * perf["breathiness"] * 0.35
    whisper = perf["whisper"]
    shaped_noise = np.convolve(rng.randn(n), np.ones(32) / 32, mode="same")
    shaped_noise = shaped_noise / (np.max(np.abs(shaped_noise)) + 1e-9) * 0.5
    voiced = (tone + breath) * (1.0 - whisper) + shaped_noise * whisper
    attack = min(n, int(SAMPLE_RATE * 0.02))
    release = min(n, int(SAMPLE_RATE * 0.05))
    env = np.ones(n)
    env[:attack] = np.linspace(0, 1, attack)
    env[-release:] *= np.linspace(1, 0, release)
    return voiced * env


def _consonant(phones: List[str], dur_s: float,
               rng: np.random.RandomState) -> np.ndarray:
    n = max(16, int(dur_s * SAMPLE_RATE))
    out = np.zeros(n)
    if any(p in _STOPS for p in phones):
        burst = rng.randn(min(n, int(SAMPLE_RATE * 0.03)))
        out[:len(burst)] = burst * np.exp(-np.arange(len(burst)) / (SAMPLE_RATE * 0.008))
    elif any(p in _FRICATIVES for p in phones):
        noise = rng.randn(n)
        hp = np.diff(noise, prepend=0.0)
        out = hp * np.linspace(0.3, 1.0, n)
    elif any(p in _NASALS_LIQUIDS for p in phones):
        tone = np.sin(2 * math.pi * 220 * np.arange(n) / SAMPLE_RATE)
        kernel = np.ones(64) / 64
        out = np.convolve(tone, kernel, mode="same") * 0.6
    else:
        out = rng.randn(n) * 0.1
    return out * 0.5


def _syllable_audio(syllable: Dict[str, Any], freq: float, dur_s: float,
                    perf: Dict[str, Any], rng: np.random.RandomState) -> np.ndarray:
    phones = syllable.get("phonemes", [])
    vowels = [p for p in phones if p in ARPABET_VOWELS]
    consonants = [p for p in phones if p not in ARPABET_VOWELS]
    cons_dur = min(0.07, dur_s * 0.3) if consonants else 0.0
    vowel_dur = max(0.03, dur_s - cons_dur)
    parts = []
    if consonants:
        parts.append(_consonant(consonants, cons_dur, rng))
    parts.append(_vowel_tone(freq, vowel_dur, perf, rng) if vowels
                 else _consonant(consonants or ["HH"], vowel_dur, rng))
    return np.concatenate(parts)


class ReferenceVocalRenderer(VocalRendererABC):
    """Deterministic reference vocal renderer."""

    @property
    def component_name(self) -> str:
        return "Vocal renderer"

    @property
    def supported_tiers(self) -> List[str]:
        return ["draft", "studio", "hosted"]

    def render_line(self, voice_id: str, lyric_line: Dict[str, Any],
                    performance: Dict[str, Any], seed: int) -> Dict[str, Any]:
        """lyric_line: output of align_lyric_line (has "alignment")."""
        perf = validate_performance(performance)
        rng = np.random.RandomState(seed)
        beat_s = 60.0 / lyric_line.get("bpm", 120.0)
        push_s = perf["timing_push_ms"] / 1000.0

        entries = lyric_line.get("alignment", [])
        total_beats = max((e["end_beats"] or 0) for e in entries) if entries else 0
        total_s = total_beats * beat_s + 0.5
        n = int(total_s * SAMPLE_RATE)
        mix = np.zeros(n)

        rendered_syllables = 0
        for entry in entries:
            if entry["status"] == "unassigned":
                continue
            notes = entry["notes"]
            start_s = (entry["start_beats"] or 0) * beat_s + push_s
            legato_overlap = 0.03 * perf["phrasing_legato"]
            for n_i, note in enumerate(notes):
                dur_s = note["duration_beats"] * beat_s + legato_overlap
                freq = _midi_to_freq(note["pitch"])
                tone = _syllable_audio(entry["syllable"], freq, dur_s, perf, rng)
                tone = tone * (0.4 + 0.6 * perf["dynamics"])
                start = int(max(0, start_s + n_i * note["duration_beats"] * beat_s) * SAMPLE_RATE)
                end = min(n, start + len(tone))
                if end > start:
                    mix[start:end] += tone[:end - start]
            rendered_syllables += 1

        # Doubles: detuned copies. Harmonies: diatonic third above.
        # (Applied as post passes over the dry line for determinism.)
        out = mix
        if perf["doubles"]:
            shifted = np.roll(mix, int(SAMPLE_RATE * 0.015))
            out = out + shifted * 0.3 * perf["doubles"] / 2
        if perf["harmonies"]:
            harm = np.zeros_like(mix)
            # A third above is roughly 1.26x; resampling the line up is the
            # honest reference approximation, marked in metadata.
            idx = (np.arange(n) * 1.26).astype(int)
            idx = idx[idx < n]
            harm[:len(idx)] = mix[idx] * 0.4
            out = out + harm * min(1.0, perf["harmonies"] / 2)

        peak = float(np.max(np.abs(out)))
        if peak > 0.95:
            out = out / peak * 0.95
        stereo = np.stack([out, out * 0.9], axis=1)

        return {
            "audio": {"samples": stereo, "sample_rate": SAMPLE_RATE},
            "metadata": {
                "voice_id": voice_id, "seed": seed,
                "performance": perf,
                "syllables_rendered": rendered_syllables,
                "warnings": [
                    "reference renderer: prosody and expressive-control path "
                    "only; not an intelligible singing voice. A learned vocal "
                    "model plugs into this interface.",
                ],
            },
        }
