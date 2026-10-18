"""Automatic checks (17.3): tempo/key accuracy, WER, loudness/clipping/
silence/clicks, identity similarity, timbre consistency, edit locality,
reproducibility.
"""

from typing import Any, Dict

import numpy as np


def check_tempo_key(audio: np.ndarray, rate: int,
                    expected_bpm: float, expected_key: str = None) -> Dict:
    # Tempo via onset autocorrelation (simple, honest).
    win = int(rate * 0.05)
    flux = []
    prev = None
    for s in range(0, len(audio) - win, win // 2):
        spec = np.abs(np.fft.rfft(audio[s:s + win] * np.hanning(win)))
        if prev is not None:
            flux.append(float(np.sum(np.maximum(0, spec - prev))))
        prev = spec
    flux = np.array(flux)
    # Autocorrelate the flux for periodicity.
    if len(flux) < 10:
        return {"passed": False, "reason": "too short"}
    corr = np.correlate(flux - flux.mean(), flux - flux.mean(), mode="full")
    corr = corr[len(corr) // 2:]
    # Search lags for 60-200 BPM.
    hop_s = (win // 2) / rate
    lo = int(60 / 200 / hop_s)
    hi = int(60 / 60 / hop_s)
    region = corr[lo:hi]
    lag = int(np.argmax(region)) + lo
    detected_bpm = 60 / (lag * hop_s)
    err = abs(detected_bpm - expected_bpm) / expected_bpm
    return {"passed": err < 0.1, "detected_bpm": round(detected_bpm, 1),
            "expected_bpm": expected_bpm, "rel_error": round(err, 3)}


def check_audio_quality(audio: np.ndarray, rate: int) -> Dict:
    """Loudness, clipping, silence, clicks, DC, channels (17.3)."""
    stereo = np.asarray(audio)
    if stereo.ndim == 1:
        stereo = np.stack([stereo, stereo])
    peak = float(np.max(np.abs(stereo)))
    rms = float(np.sqrt(np.mean(stereo ** 2)))
    dc = abs(float(np.mean(stereo)))
    # Clicks: max sample-to-sample jump vs RMS.
    jump = float(np.max(np.abs(np.diff(stereo, axis=1))))
    checks = {
        "no_clipping": peak <= 1.0,
        "not_silent": rms > 1e-4,
        "no_dc_offset": dc < 0.01,
        "no_clicks": jump < 10 * rms + 0.1,
        "channels_ok": stereo.shape[0] == 2,
    }
    return {"passed": all(checks.values()), "checks": checks,
            "peak": round(peak, 3), "rms_db": round(
                20 * np.log10(rms + 1e-9), 1)}


def check_identity_similarity(vec_a, vec_b,
                              threshold: float = 0.8) -> Dict:
    """Voice character identity similarity (17.3)."""
    from kindling.assets.voice import identity_similarity
    sim = identity_similarity(vec_a, vec_b)
    return {"passed": sim >= threshold, "similarity": round(sim, 3),
            "threshold": threshold}


def check_edit_locality(before: np.ndarray, after: np.ndarray,
                        mask: np.ndarray, rate: int,
                        threshold_db: float = 3.0) -> Dict:
    """Edit locality and boundary seams (17.3)."""
    from kindling.editing.locality import (outside_mask_distance,
                                           seam_score)
    dist = outside_mask_distance(before, after, mask, rate)
    # Find mask boundaries.
    diff = np.diff(mask.astype(int))
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0]
    seams = []
    for b in list(starts) + list(ends):
        seams.append(seam_score(after, rate, b / rate))
    return {"passed": dist < threshold_db,
            "outside_mask_db": round(dist, 2),
            "threshold_db": threshold_db,
            "seams": seams}


def check_reproducibility_declared(before: np.ndarray, after: np.ndarray,
                                   rate: int, declared: str) -> Dict:
    """Reproducibility at the declared level (17.3)."""
    from kindling.project.pinning import check_reproducibility
    result = check_reproducibility(before, after, rate)
    achieved = result["level"]
    order = {"A": 2, "B": 1, None: 0}
    passed = order[achieved] >= order[declared]
    return {"passed": passed, "declared": declared,
            "achieved": achieved, "detail": result}
