"""Codec evaluation harness (Part 5, acceptance tests).

A codec MUST be evaluated on its own before any generator is built on it.
Objective checks: spectral error, transient smearing, stereo correlation,
and loudness drift. Plus encode-edit-decode round trips proving no seams at
region boundaries. Listening tests follow the protocol in
docs/listening-protocol.md; this harness runs the objective half in CI.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

import numpy as np

from kindling.codec.codec import FramedCodec


def _stft_mag(samples: np.ndarray, frame: int = 4096, hop: int = 2048) -> np.ndarray:
    window = np.hanning(frame)
    mags = []
    for start in range(0, len(samples) - frame, hop):
        mags.append(np.abs(np.fft.rfft(samples[start:start + frame] * window)))
    return np.array(mags)


def spectral_error_db(original: np.ndarray, reconstructed: np.ndarray) -> float:
    """Mean absolute log-spectral distance in dB across frames.

    Two guards keep the metric honest. The floor sits 100 dB below the signal
    peak, so near-silent bins measure the codec, not the arithmetic floor.
    Per frame, only bins within 60 dB of the frame peak count: differences
    buried deeper than that are inaudible under the frame's own content, and
    counting them would punish quantization noise in valleys nobody hears.
    """
    o = _stft_mag(original)
    r = _stft_mag(reconstructed)
    n = min(len(o), len(r))
    if n == 0:
        return float("inf")
    peak = max(float(o.max(initial=0.0)), 1e-12)
    floor = peak * 1e-5
    log_o = 20 * np.log10(np.maximum(o[:n], floor))
    log_r = 20 * np.log10(np.maximum(r[:n], floor))
    diffs = []
    for i in range(n):
        frame_peak = log_o[i].max()
        mask = log_o[i] >= frame_peak - 60.0
        if mask.any():
            diffs.append(float(np.mean(np.abs(log_o[i][mask] - log_r[i][mask]))))
    return float(np.mean(diffs)) if diffs else 0.0


def _onset_flux(samples: np.ndarray, rate: int) -> np.ndarray:
    frame, hop = 1024, 256
    window = np.hanning(frame)
    fluxes = []
    prev = np.zeros(frame // 2 + 1)
    for start in range(0, len(samples) - frame, hop):
        mag = np.abs(np.fft.rfft(samples[start:start + frame] * window))
        fluxes.append(max(0.0, float(((mag - prev).clip(min=0) ** 2).sum())))
        prev = mag
    return np.array(fluxes)


def transient_preservation(original: np.ndarray, reconstructed: np.ndarray,
                           rate: int) -> float:
    """For each strong onset in the original, how much of its flux survives
    nearby in the reconstruction. 1.0 means transients are untouched."""
    fo = _onset_flux(original, rate)
    fr = _onset_flux(reconstructed, rate)
    n = min(len(fo), len(fr))
    fo, fr = fo[:n], fr[:n]
    if fo.max() <= 0:
        return 1.0
    threshold = fo.mean() + fo.std()
    peaks = [i for i in range(1, n - 1)
             if fo[i] > threshold and fo[i] >= fo[i - 1] and fo[i] >= fo[i + 1]]
    if not peaks:
        return 1.0
    ratios = []
    for i in peaks:
        lo, hi = max(0, i - 2), min(n, i + 3)
        ratios.append(fr[lo:hi].max() / (fo[i] + 1e-12))
    return float(min(1.0, float(np.mean(ratios))))


def stereo_correlation(original: np.ndarray, reconstructed: np.ndarray) -> Dict[str, float]:
    """Per-channel correlation plus correlation of the stereo difference
    (L-R), which is what carries the stereo image."""
    o = np.asarray(original, dtype=float)
    r = np.asarray(reconstructed, dtype=float)
    n = min(len(o), len(r))
    o, r = o[:n], r[:n]
    if o.ndim == 1:
        o = np.stack([o, o], axis=1)
    if r.ndim == 1:
        r = np.stack([r, r], axis=1)

    def corr(a: np.ndarray, b: np.ndarray) -> float:
        a, b = a - a.mean(), b - b.mean()
        denom = math.sqrt(float((a ** 2).sum() * (b ** 2).sum()))
        return float((a * b).sum() / denom) if denom > 0 else 1.0

    return {
        "left": corr(o[:, 0], r[:, 0]),
        "right": corr(o[:, 1], r[:, 1]),
        "stereo_diff": corr(o[:, 0] - o[:, 1], r[:, 0] - r[:, 1]),
    }


def loudness_drift_db(original: np.ndarray, reconstructed: np.ndarray,
                       rate: int, window_s: float = 0.4) -> float:
    """Worst windowed RMS level difference in dB. Windows where the original
    sits below -60 dBFS are skipped: down there the metric would measure
    quantization noise against silence, not the codec."""
    w = int(rate * window_s)
    worst = 0.0
    for start in range(0, min(len(original), len(reconstructed)) - w, w):
        ro = float(np.sqrt(np.mean(original[start:start + w] ** 2)))
        if 20 * math.log10(ro + 1e-12) < -60:
            continue
        rr = float(np.sqrt(np.mean(reconstructed[start:start + w] ** 2)))
        ro_db = 20 * math.log10(ro + 1e-12)
        rr_db = 20 * math.log10(rr + 1e-12)
        worst = max(worst, abs(ro_db - rr_db))
    return worst


def seam_energy(original_full_decode: np.ndarray, region_decode: np.ndarray,
                region_start: int) -> float:
    """Max absolute sample difference where a region decode meets the full
    decode. Frame-aligned regions must be bit-exact: energy zero."""
    a = original_full_decode[region_start:region_start + len(region_decode)]
    return float(np.max(np.abs(a - region_decode))) if len(a) else 0.0


# ---------------------------------------------------------------- signals
def _stereo(mono: np.ndarray, width: float = 0.6) -> np.ndarray:
    return np.stack([mono, mono * width], axis=1)


def _norm(stereo: np.ndarray, peak: float = 0.95) -> np.ndarray:
    m = float(np.max(np.abs(stereo)))
    return stereo / m * peak if m > peak else stereo


def test_signals(rate: int = 48000, seconds: float = 4.0) -> Dict[str, np.ndarray]:
    """Deterministic signals standing in for the five acceptance categories:
    drums, vocals, solo piano, dense mix, quiet material."""
    rng = np.random.RandomState(7)
    n = int(seconds * rate)
    t = np.arange(n) / rate

    drums = np.zeros(n)
    for beat in range(0, n, int(rate * 0.5)):
        burst = rng.randn(min(900, n - beat)) * np.exp(-np.arange(min(900, n - beat)) / 120)
        drums[beat:beat + len(burst)] += burst * 0.9

    f0 = 220.0
    vibrato = 6.0 * np.sin(2 * math.pi * 5.5 * t)
    vocal = sum(np.sin(2 * math.pi * (f0 * (1 + vibrato / f0)) * h * t) / h
                for h in range(1, 7)) / 3.0
    vocal *= 0.5 + 0.5 * np.sin(2 * math.pi * 0.4 * t) ** 2

    piano = np.zeros(n)
    for i, freq in enumerate([261.63, 329.63, 392.0, 523.25]):
        start = int(i * rate * 0.9)
        length = min(n - start, int(rate * 1.6))
        tt = np.arange(length) / rate
        tone = sum(np.sin(2 * math.pi * freq * h * tt) / (h ** 1.5) for h in range(1, 5))
        piano[start:start + length] += tone * np.exp(-tt * 2.2) * 0.5

    drums_s = _stereo(drums * 0.8)
    vocal_s = _stereo(vocal * 0.7)
    piano_s = _stereo(piano)
    bass = 0.4 * np.sin(2 * math.pi * 55 * t)
    bass_s = np.stack([bass, bass * 0.8], axis=1)
    dense = drums_s * 0.5 + vocal_s * 0.4 + piano_s * 0.5 + bass_s * 0.7
    peak = float(np.max(np.abs(dense)))
    if peak > 0.95:
        dense = dense / peak * 0.95

    quiet = 0.01 * np.sin(2 * math.pi * 1000 * t)

    return {
        "drums": _norm(drums_s),
        "vocals": _norm(vocal_s),
        "piano": _norm(piano_s),
        "dense_mix": _norm(dense),
        "quiet": _stereo(quiet),
    }


THRESHOLDS = {
    "draft": {"spectral_error_db": 8.0, "transient_preservation": 0.85,
              "stereo_corr": 0.99, "loudness_drift_db": 0.6, "seam": 1e-9},
    "hifi": {"spectral_error_db": 0.5, "transient_preservation": 0.999,
             "stereo_corr": 0.9999, "loudness_drift_db": 0.05, "seam": 1e-9},
}


def evaluate_codec(codec: FramedCodec, rate: int = 48000) -> Dict[str, Any]:
    """Run the full objective acceptance battery. Returns per-signal metrics
    and a pass/fail per threshold."""
    thresholds = THRESHOLDS[codec.rate]
    signals = test_signals(rate=rate)
    per_signal = {}
    all_pass = True
    for name, stereo in signals.items():
        tokens = codec.encode({"samples": stereo, "sample_rate": rate})
        recon = codec.decode(tokens)["samples"]
        mono_o = stereo.mean(axis=1)
        mono_r = recon.mean(axis=1)
        spec_err = spectral_error_db(mono_o, mono_r)
        trans = transient_preservation(mono_o, mono_r, rate)
        scorr = stereo_correlation(stereo, recon)
        drift = loudness_drift_db(mono_o, mono_r, rate)

        region = codec.decode_region(tokens, 1.0, 2.0)
        start = region["region_start_sample"]
        seam = seam_energy(recon, region["samples"][:len(recon) - start], start)

        checks = {
            "spectral_error_db": spec_err <= thresholds["spectral_error_db"],
            "transient_preservation": trans >= thresholds["transient_preservation"],
            "stereo_corr": min(scorr.values()) >= thresholds["stereo_corr"],
            "loudness_drift_db": drift <= thresholds["loudness_drift_db"],
            "seam": seam <= thresholds["seam"],
        }
        passed = all(checks.values())
        all_pass = all_pass and passed
        per_signal[name] = {
            "spectral_error_db": round(spec_err, 3),
            "transient_preservation": round(trans, 4),
            "stereo_correlation": {k: round(v, 5) for k, v in scorr.items()},
            "loudness_drift_db": round(drift, 4),
            "seam_max_diff": seam,
            "checks": checks,
            "passed": passed,
        }
    return {"codec": "kindling-framed", "rate": codec.rate,
            "thresholds": thresholds, "signals": per_signal,
            "passed": all_pass}
