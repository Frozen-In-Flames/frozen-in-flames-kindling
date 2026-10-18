"""Reference analysis for inverse rendering (10.1, step 1).

Measures what a finished recording demonstrates: tonal balance,
dynamics, stereo image, space, and per-section changes. Source roles
are detected from spectral/temporal signatures. This is the evidence
the preset inference works from.
"""

from typing import Any, Dict, List

import numpy as np


def _spectral_centroid(sig: np.ndarray, rate: int) -> float:
    spec = np.abs(np.fft.rfft(sig * np.hanning(len(sig)))[:len(sig)//2])
    freqs = np.fft.rfftfreq(len(sig), 1.0 / rate)[:len(sig)//2]
    return float((freqs * spec).sum() / (spec.sum() + 1e-12))


def _band_energies(sig: np.ndarray, rate: int) -> Dict[str, float]:
    bands = {"sub": (20, 120), "low": (120, 400), "mid": (400, 2500),
             "high": (2500, 8000), "air": (8000, 20000)}
    spec = np.abs(np.fft.rfft(sig * np.hanning(len(sig))))
    freqs = np.fft.rfftfreq(len(sig), 1.0 / rate)
    total = spec.sum() + 1e-12
    return {name: float(spec[(freqs >= lo) & (freqs < hi)].sum() / total)
            for name, (lo, hi) in bands.items()}


def analyze_reference(audio: np.ndarray, rate: int,
                      sections: List[Dict[str, float]] = None) -> Dict[str, Any]:
    """Analyze a finished stereo (or mono) recording.

    sections: [{"name", "start_s", "end_s"}]. If omitted, the whole
    track is one section.
    """
    if audio.ndim == 1:
        audio = np.stack([audio, audio])
    left, right = audio[0], audio[1]
    mid = (left + right) / 2
    side = (left - right) / 2

    # Tonal balance and dynamics on the mid signal.
    tonal = _band_energies(mid, rate)
    rms = float(np.sqrt(np.mean(mid ** 2)))
    peak = float(np.max(np.abs(mid)))
    crest_db = 20 * np.log10(peak / (rms + 1e-9))

    # Stereo image: correlation and side/mid energy ratio.
    corr = float(np.corrcoef(left, right)[0, 1]) if len(left) > 1 else 1.0
    side_db = 20 * np.log10(np.sqrt(np.mean(side ** 2)) / (rms + 1e-9))

    # Space: late energy ratio (simple: energy after 80 ms of autocorrelation
    # envelope decay vs early). Estimated from the amplitude envelope's
    # decay tail.
    env = np.abs(mid)
    win = int(rate * 0.5)
    tails = []
    for s in range(0, len(env) - win, win):
        seg = env[s:s + win]
        early = seg[:int(rate * 0.08)].mean()
        late = seg[int(rate * 0.08):].mean()
        if early > 1e-6:
            tails.append(late / early)
    space_ratio = float(np.mean(tails)) if tails else 0.0

    result = {
        "tonal_balance": {k: round(v, 4) for k, v in tonal.items()},
        "spectral_centroid_hz": round(_spectral_centroid(mid, rate), 1),
        "crest_db": round(crest_db, 2),
        "stereo_correlation": round(corr, 3),
        "side_db": round(side_db, 2),
        "space_ratio": round(space_ratio, 4),
        "duration_s": round(len(mid) / rate, 2),
    }

    # Per-section changes (10.1: "per-section changes").
    if sections:
        per_section = []
        for sec in sections:
            s0, s1 = int(sec["start_s"] * rate), int(sec["end_s"] * rate)
            seg = mid[s0:s1]
            if len(seg) < rate:
                continue
            per_section.append({
                "name": sec["name"],
                "tonal_balance": {k: round(v, 4)
                                  for k, v in _band_energies(seg, rate).items()},
                "centroid_hz": round(_spectral_centroid(seg, rate), 1),
                "rms_db": round(20 * np.log10(
                    np.sqrt(np.mean(seg ** 2)) + 1e-9), 2),
            })
        result["per_section"] = per_section

    # Role detection: crude but real (low rumble -> bass role, broadband
    # transient density -> drums role, harmonic mid -> keys/guitar role).
    roles = []
    if tonal["sub"] + tonal["low"] > 0.45:
        roles.append("bass")
    if crest_db > 12:
        roles.append("drums")
    if 0.2 < tonal["mid"] < 0.7:
        roles.append("harmonic")
    if tonal["high"] + tonal["air"] > 0.25:
        roles.append("bright_lead")
    result["detected_roles"] = roles or ["full_mix"]
    return result
