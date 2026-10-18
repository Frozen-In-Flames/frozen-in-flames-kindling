"""Mastering stage (13.2): optional, separable, never silent.

Offers loudness targets for common destinations, optional reference
matching, and a bypass. The mastering report states exactly what was
applied; bypass returns the mix untouched.
"""

import math
from typing import Any, Dict

import numpy as np

from .mixer import k_weighted_loudness, true_peak

# Loudness targets for common destinations (LUFS).
LOUDNESS_TARGETS = {
    "streaming": -14.0,
    "club": -9.0,
    "broadcast": -16.0,
    "cinema": -20.0,
}


def _limiter(stereo: np.ndarray, rate: int, ceiling_db: float = -1.0,
             release_ms: float = 50.0) -> np.ndarray:
    """Simple lookahead-ish limiter (one-pole release envelope)."""
    ceiling = 10 ** (ceiling_db / 20.0)
    mono = np.mean(np.abs(stereo), axis=0) if stereo.ndim > 1 else np.abs(stereo)
    release = math.exp(-1.0 / (rate * release_ms / 1000.0))
    env = 0.0
    gain = np.ones(len(mono))
    for i in range(len(mono)):
        env = max(mono[i], env * release)
        if env > ceiling:
            gain[i] = ceiling / (env + 1e-9)
    # Smooth.
    coef = 0.995
    smooth = np.zeros_like(gain)
    smooth[0] = gain[0]
    for i in range(1, len(gain)):
        smooth[i] = min(gain[i], smooth[i - 1] * coef + gain[i] * (1 - coef))
    if stereo.ndim > 1:
        return stereo * smooth
    return stereo * smooth


def master(mix: np.ndarray, rate: int,
           target: str = "streaming",
           reference_lufs: float = None,
           bypass: bool = False) -> Dict[str, Any]:
    """Master the mix. Returns {"audio", "report"}.

    If bypass, the audio is returned untouched and the report says so.
    Never apply mastering silently: the report always lists what ran.
    """
    if bypass:
        return {"audio": mix,
                "report": {"mastering": "bypassed",
                           "applied": [],
                           "loudness_lufs": k_weighted_loudness(mix, rate),
                           "true_peak_dbfs": true_peak(mix)}}
    if target not in LOUDNESS_TARGETS:
        raise ValueError(f"unknown target {target!r}")
    target_lufs = reference_lufs if reference_lufs is not None \
        else LOUDNESS_TARGETS[target]
    applied = []

    current = k_weighted_loudness(mix, rate)
    gain_db = target_lufs - current
    # Limit gain to a sane range.
    gain_db = max(-12.0, min(12.0, gain_db))
    out = mix * (10 ** (gain_db / 20.0))
    applied.append(f"gain {gain_db:+.1f} dB to {target_lufs} LUFS")

    out = _limiter(out, rate, ceiling_db=-1.0)
    applied.append("limiter ceiling -1.0 dBFS")

    report = {"mastering": "applied", "applied": applied,
              "target": target, "target_lufs": target_lufs,
              "loudness_lufs": k_weighted_loudness(out, rate),
              "true_peak_dbfs": true_peak(out),
              "reference_matched": reference_lufs is not None}
    return {"audio": out, "report": report}
