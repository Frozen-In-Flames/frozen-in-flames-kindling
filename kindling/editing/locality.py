"""Locality (12.3): edit masks, perceptual distance, seam measurement.

A targeted edit MUST mostly affect the requested area. We define an edit
mask per operation, measure the difference outside the mask, check seams
at boundaries, and verify locked elements are unchanged.
"""

from typing import Any, Dict, List, Tuple

import numpy as np


def edit_mask(num_samples: int, rate: int,
              start_s: float, end_s: float) -> np.ndarray:
    """Boolean mask: True inside the edited time range."""
    mask = np.zeros(num_samples, dtype=bool)
    s0 = max(0, int(start_s * rate))
    s1 = min(num_samples, int(end_s * rate))
    mask[s0:s1] = True
    return mask


def perceptual_distance(a: np.ndarray, b: np.ndarray,
                        rate: int) -> float:
    """Mean absolute log-spectral difference (dB) over 50 ms frames.

    A simple perceptual distance for the reference implementation.
    Production would use a trained metric; this is honest DSP.
    """
    n = min(len(a), len(b))
    if n < rate * 0.05:
        return 0.0
    win = int(rate * 0.05)
    dists = []
    for s in range(0, n - win, win):
        sa = np.abs(np.fft.rfft(a[s:s + win] * np.hanning(win))) + 1e-9
        sb = np.abs(np.fft.rfft(b[s:s + win] * np.hanning(win))) + 1e-9
        dists.append(float(np.mean(np.abs(20 * np.log10(sa / sb)))))
    return float(np.mean(dists)) if dists else 0.0


def outside_mask_distance(before: np.ndarray, after: np.ndarray,
                          mask: np.ndarray, rate: int) -> float:
    """Perceptual distance OUTSIDE the edit mask (12.3)."""
    idx = np.where(~mask)[0]
    if len(idx) < rate * 0.05:
        return 0.0
    return perceptual_distance(before[idx], after[idx], rate)


def seam_score(audio: np.ndarray, rate: int,
               boundary_s: float) -> Dict[str, float]:
    """Measure clicks/level jumps at a mask boundary (12.3)."""
    b = int(boundary_s * rate)
    w = int(rate * 0.02)  # 20 ms each side
    if b < w or b + w > len(audio):
        return {"click_db": 0.0, "level_jump_db": 0.0}
    left = audio[b - w:b]
    right = audio[b:b + w]
    # Click: high-frequency energy spike at the boundary.
    mid = audio[max(0, b - 64):b + 64]
    click = float(np.max(np.abs(np.diff(mid))))
    # Level jump: RMS ratio across the boundary.
    rms_l = float(np.sqrt(np.mean(left ** 2)) + 1e-9)
    rms_r = float(np.sqrt(np.mean(right ** 2)) + 1e-9)
    jump_db = abs(20 * np.log10(rms_r / rms_l))
    return {"click_db": round(20 * np.log10(click + 1e-9), 1),
            "level_jump_db": round(jump_db, 2)}


def verify_locked(before: Dict[str, np.ndarray],
                  after: Dict[str, np.ndarray],
                  lock_set: List[str]) -> Dict[str, str]:
    """Locked elements MUST be unchanged. Returns element -> guarantee.

    "bit-exact" if sample-identical, "perceptual" if within 0.5 dB,
    raises if changed beyond that.
    """
    result = {}
    for element in lock_set:
        if element not in before or element not in after:
            continue
        a, b = before[element], after[element]
        if a.shape == b.shape and np.array_equal(a, b):
            result[element] = "bit-exact"
            continue
        # Fallback for short signals: RMS difference in dB.
        n = min(len(a), len(b))
        rms_diff = float(np.sqrt(np.mean((a[:n] - b[:n]) ** 2)))
        rms_ref = float(np.sqrt(np.mean(a[:n] ** 2)) + 1e-9)
        diff_db = 20 * np.log10(rms_diff / rms_ref + 1e-9)
        if diff_db < -40:
            result[element] = "perceptual"
        elif n >= 2400 and perceptual_distance(a, b, 48000) < 0.5:
            result[element] = "perceptual"
        else:
            raise ValueError(f"locked element {element!r} changed")
    return result


def crossfade_edits(before: np.ndarray, edited_region: np.ndarray,
                    rate: int, start_s: float, end_s: float,
                    fade_ms: float = 10.0) -> np.ndarray:
    """Splice an edited region with crossfades to avoid seams."""
    out = before.copy()
    s0, s1 = int(start_s * rate), int(end_s * rate)
    f = int(rate * fade_ms / 1000.0)
    region = edited_region[:s1 - s0]
    if len(region) < s1 - s0:
        padded = np.zeros(s1 - s0)
        padded[:len(region)] = region
        region = padded
    # Crossfade in.
    if f > 0 and s0 >= f:
        fade_in = np.linspace(0, 1, f)
        region[:f] = region[:f] * fade_in + out[s0:s0 + f] * (1 - fade_in)
    # Crossfade out.
    if f > 0 and s1 + f <= len(out):
        fade_out = np.linspace(1, 0, f)
        tail = region[-f:] * fade_out + out[s1 - f:s1] * (1 - fade_out)
        region[-f:] = tail
    out[s0:s1] = region
    return out
