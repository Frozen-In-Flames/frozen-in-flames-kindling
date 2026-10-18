"""Sample-map instrument renderer (Phase A).

Plays slices of an uploaded recording pitched to requested notes. Slice
choice is nearest-root-pitch; pitch shift is linear-interp resampling by
the semitone ratio. Unpitched instruments cycle slices in order. Fully
deterministic: same notes, same audio, every time.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np


def _pitch_shift(slice_audio: np.ndarray, semitones: float) -> np.ndarray:
    if abs(semitones) < 0.01:
        return slice_audio
    ratio = 2.0 ** (semitones / 12.0)
    n_out = max(1, int(len(slice_audio) / ratio))
    idx = np.linspace(0, len(slice_audio) - 1, n_out)
    return np.interp(idx, np.arange(len(slice_audio)),
                     slice_audio).astype(np.float32)


def _fade(sig: np.ndarray, rate: int, ms: float = 5.0) -> np.ndarray:
    n = min(len(sig), max(1, int(rate * ms / 1000.0)))
    if n <= 1:
        return sig
    ramp = np.linspace(0.0, 1.0, n).astype(np.float32)
    out = sig.copy()
    out[:n] *= ramp
    out[-n:] *= ramp[::-1]
    return out


def render_sample_instrument(payload: Dict[str, Any], audio_mono: np.ndarray,
                             notes: List[Dict[str, Any]], rate: int,
                             seed: int = 0) -> np.ndarray:
    """Render notes through a sample-map instrument payload.

    notes: [{midi, start_s, dur_s, vel}]. Returns mono float32.
    """
    slices = payload.get("slices", [])
    if not slices:
        raise ValueError("sample instrument has no slices")
    unpitched = payload.get("unpitched", False)
    total_s = max((n["start_s"] + n["dur_s"] for n in notes), default=0.0)
    out = np.zeros(int(total_s * rate) + rate, dtype=np.float32)
    cycle = 0
    for note in notes:
        if unpitched:
            sl = slices[cycle % len(slices)]
            cycle += 1
            shifted = audio_mono[int(sl["start_s"] * rate):
                                 int((sl["start_s"] + sl["dur_s"]) * rate)]
        else:
            pitched = [s for s in slices if s.get("root_midi") is not None]
            pool = pitched or slices
            sl = min(pool, key=lambda s: abs((s.get("root_midi") or 60)
                                             - note["midi"]))
            raw = audio_mono[int(sl["start_s"] * rate):
                             int((sl["start_s"] + sl["dur_s"]) * rate)]
            semis = note["midi"] - (sl.get("root_midi") or 60.0)
            # Clamp absurd shifts: beyond 2 octaves the slice is the wrong
            # tool; pick is already nearest, this is a safety rail.
            semis = max(-24.0, min(24.0, semis))
            shifted = _pitch_shift(raw, semis)
        want = int(note["dur_s"] * rate)
        take = shifted[:want] if len(shifted) >= want else np.pad(
            shifted, (0, want - len(shifted)))
        take = _fade(take, rate) * float(note.get("vel", 0.8))
        start = int(note["start_s"] * rate)
        end = min(len(out), start + len(take))
        if end > start:
            out[start:end] += take[:end - start]
    peak = float(np.max(np.abs(out)))
    if peak > 0.95:
        out = out / peak * 0.95
    return out
