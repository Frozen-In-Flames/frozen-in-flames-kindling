"""Reference song renderer (Part 6.3).

Stable interface: scene fragment in, audio and metadata out. This reference
implementation renders deterministically with simple synthesis: plucked,
pad, and bass tones per note, noise-based drums, and a soft guide tone for
vocal parts (real vocal rendering is Part 7; the metadata says so plainly).
No learned model is faked. The same seed and scene always produce the same
audio, which is what makes preview tiers and the bake-off meaningful.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np

from kindling.interfaces import SongRenderer as SongRendererABC

PREVIEW_LENGTH_S = 8.0


def _midi_to_freq(pitch: int) -> float:
    return 440.0 * (2.0 ** ((pitch - 69) / 12.0))


def _pluck(freq: float, dur: float, rate: int) -> np.ndarray:
    n = max(1, int(dur * rate))
    t = np.arange(n) / rate
    tone = sum(np.sin(2 * math.pi * freq * h * t) / (h ** 1.5) for h in range(1, 7))
    return tone * np.exp(-t * 3.0) * 0.5


def _pad(freq: float, dur: float, rate: int) -> np.ndarray:
    n = max(1, int(dur * rate))
    t = np.arange(n) / rate
    tone = sum(np.sin(2 * math.pi * freq * h * t) / h for h in range(1, 4))
    attack = min(n, int(rate * 0.3))
    env = np.ones(n)
    env[:attack] = np.linspace(0, 1, attack)
    env[-min(n, int(rate * 0.3)):] *= np.linspace(1, 0, min(n, int(rate * 0.3)))
    return tone * env * 0.25


def _bass(freq: float, dur: float, rate: int) -> np.ndarray:
    n = max(1, int(dur * rate))
    t = np.arange(n) / rate
    tone = np.sin(2 * math.pi * freq * t) + 0.3 * np.sin(2 * math.pi * freq * 2 * t)
    env = np.exp(-t * 1.5)
    return tone * env * 0.6


def _kick(rate: int) -> np.ndarray:
    n = int(rate * 0.25)
    t = np.arange(n) / rate
    freq = 120 * np.exp(-t * 30) + 40
    phase = 2 * math.pi * np.cumsum(freq) / rate
    return np.sin(phase) * np.exp(-t * 18) * 0.9


def _snare(rate: int, rng: np.random.RandomState) -> np.ndarray:
    n = int(rate * 0.2)
    t = np.arange(n) / rate
    noise = rng.randn(n)
    return (noise * 0.5 + np.sin(2 * math.pi * 180 * t) * 0.4) * np.exp(-t * 25) * 0.7


def _hat(rate: int, rng: np.random.RandomState) -> np.ndarray:
    n = int(rate * 0.08)
    noise = rng.randn(n)
    hp = np.diff(noise, prepend=0.0)
    return hp * np.exp(-np.arange(n) / rate * 120) * 0.4


_DRUM_CACHE: Dict[str, np.ndarray] = {}


def _drum_hit(pitch: int, rate: int, rng: np.random.RandomState) -> np.ndarray:
    key = f"{pitch}@{rate}"
    if key not in _DRUM_CACHE:
        if pitch <= 40:
            _DRUM_CACHE[key] = _kick(rate)
        elif pitch <= 50:
            _DRUM_CACHE[key] = _snare(rate, np.random.RandomState(pitch))
        else:
            _DRUM_CACHE[key] = _hat(rate, np.random.RandomState(pitch))
    return _DRUM_CACHE[key]


def _render_note(freq: float, dur: float, rate: int, role: str,
                 rng: np.random.RandomState) -> np.ndarray:
    if role in ("drums", "percussion"):
        return _np_copy(_drum_hit(int(round(69 + 12 * math.log2(freq / 440.0))), rate, rng))
    if role == "bass":
        return _bass(freq, dur, rate)
    if role in ("pad", "strings"):
        return _pad(freq, dur, rate)
    return _pluck(freq, dur, rate)


def _np_copy(arr: np.ndarray) -> np.ndarray:
    return np.array(arr, dtype=float)


class ReferenceRenderer(SongRendererABC):
    """Deterministic reference renderer. approach = "reference-deterministic"."""

    approach = "reference-deterministic"

    def __init__(self, humanize: bool = True):
        self.humanize = humanize

    @property
    def component_name(self) -> str:
        return "Song renderer"

    @property
    def supported_tiers(self) -> List[str]:
        return ["draft", "studio", "hosted"]

    def render_fragment(self, scene_fragment: Dict[str, Any], assets: Dict[str, Any],
                        seed: int, tier: str) -> Dict[str, Any]:
        rng = np.random.RandomState(seed)
        rate = scene_fragment.get("render", {}).get("sample_rate", 48000)
        bpm = scene_fragment["timeline"]["tempo"][0]["bpm"]
        beat_s = 60.0 / bpm
        warnings: List[str] = []

        total_beats = 0.0
        for part in scene_fragment.get("parts", []):
            for note in part.get("notes", []):
                total_beats = max(total_beats, note["start_beats"] + note["duration_beats"])
        for section in scene_fragment.get("sections", []):
            bars = section["bars"][1] - section["bars"][0] + 1
            total_beats = max(total_beats, bars * 4.0)
        total_s = total_beats * beat_s
        n = max(1, int(total_s * rate))
        mix = np.zeros(n)

        parts_rendered = []
        for part in scene_fragment.get("parts", []):
            role = part.get("role", "keys")
            for note in part.get("notes", []):
                start_s = note["start_beats"] * beat_s
                dur_s = note["duration_beats"] * beat_s
                if self.humanize:
                    start_s += float(rng.uniform(-0.004, 0.004))
                freq = _midi_to_freq(note["pitch"])
                tone = _render_note(freq, dur_s, rate, role, rng)
                tone = tone * note.get("velocity", 0.8)
                start = int(max(0, start_s) * rate)
                end = min(n, start + len(tone))
                if end > start:
                    mix[start:end] += tone[:end - start]
            parts_rendered.append(part["id"])

        for vocal in scene_fragment.get("vocals", []):
            warnings.append(
                f"vocal {vocal['id']!r}: guide tone only; real vocal rendering is Part 7")
            guide = _pad(_midi_to_freq(60), total_s, rate) * 0.15
            mix[:len(guide)] += guide[:n]

        peak = float(np.max(np.abs(mix)))
        if peak > 0.95:
            mix = mix / peak * 0.95
        stereo = np.stack([mix, mix * 0.9], axis=1)

        return {
            "audio": {"samples": stereo, "sample_rate": rate},
            "metadata": {
                "seed": seed, "tier": tier, "sample_rate": rate,
                "duration_s": round(total_s, 3),
                "parts_rendered": parts_rendered,
                "approach": self.approach,
                "warnings": warnings,
            },
        }

    def render_preview(self, scene: Dict[str, Any], assets: Dict[str, Any],
                       seed: int, preview: str = "draft") -> Dict[str, Any]:
        """Preview tiers (Part 6.6): sketch (first seconds, lowest cost),
        draft (full, good enough for decisions), final (full quality)."""
        import copy
        if preview == "sketch":
            frag = copy.deepcopy(scene)
            frag["render"] = dict(scene.get("render", {}))
            frag["render"]["sample_rate"] = 22050
            result = self.render_fragment(frag, assets, seed, "draft")
            samples = result["audio"]["samples"]
            keep = int(PREVIEW_LENGTH_S * 22050)
            result["audio"]["samples"] = samples[:keep]
            result["metadata"]["preview"] = "sketch"
            return result
        if preview == "draft":
            frag = copy.deepcopy(scene)
            frag["render"] = dict(scene.get("render", {}))
            frag["render"]["sample_rate"] = 44100
            result = self.render_fragment(frag, assets, seed, "draft")
            result["metadata"]["preview"] = "draft"
            return result
        result = self.render_fragment(scene, assets, seed, "studio")
        result["metadata"]["preview"] = "final"
        return result
