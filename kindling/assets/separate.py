"""Vocal / accompaniment separation with classical DSP only.

No learned models, no downloaded weights, no GPU: numpy and scipy only,
deterministic, runs anywhere. Two cues, combined per time-frequency bin:

1. Center channel. In mastered mixes the lead vocal sits panned center.
   Per STFT bin, the mid/side power ratio says how centered the content is.
2. Repeating background (REPET-style, after Rafii and Pardo). Loop-based
   accompaniment repeats; the vocal does not. The loop period is found by
   autocorrelation of the frame-energy envelope, the repeating spectrogram
   is estimated by median aggregation over whole periods, and bins
   that match it are treated as accompaniment.

A bin must look BOTH centered and non-repeating to count as vocal. That
is the whole trick: kick and bass are centered but they repeat, so the
REPET cue rejects them; wide hats and stereo instruments do not repeat
in place, but the center cue rejects them.

Honest limits, stated up front: this works best on centered vocals over
repetitive beats, which is exactly the shape of a loop-built catalog.
Residual bleed remains on wide-panned ad-libs, heavy vocal reverb tails,
and anything the accompaniment does once and never repeats. It is a
bleed reducer for reference analysis, not a studio stem splitter.
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
from scipy import signal

__all__ = ["separate_vocals", "highpass", "estimate_loop_period_frames"]

# STFT resolution. Fixed so results are identical on every machine.
_NPERSEG = 2048
_NOVERLAP = 1536
_WINDOW = "hann"


def _as_stereo(audio: np.ndarray) -> Tuple[np.ndarray, bool]:
    """Return (2, N) float64 and whether the input was mono."""
    arr = np.asarray(audio, dtype=np.float64)
    if arr.ndim == 1:
        return np.stack([arr, arr]), True
    if arr.ndim == 2 and arr.shape[0] == 2:
        return arr, False
    raise ValueError(
        f"separate_vocals needs mono (N,) or stereo (2, N); got shape {arr.shape}")


def _stft_pair(stereo: np.ndarray):
    hop = _NPERSEG - _NOVERLAP
    out = []
    for ch in stereo:
        _, _, z = signal.stft(ch, window=_WINDOW, nperseg=_NPERSEG,
                              noverlap=_NOVERLAP, boundary="zeros")
        out.append(z)
    return out[0], out[1], hop


def _istft_trim(z: np.ndarray, n: int) -> np.ndarray:
    _, x = signal.istft(z, window=_WINDOW, nperseg=_NPERSEG,
                        noverlap=_NOVERLAP)
    x = np.asarray(x, dtype=np.float64)
    if len(x) > n:
        return x[:n]
    if len(x) < n:
        return np.pad(x, (0, n - len(x)))
    return x


def estimate_loop_period_frames(mag: np.ndarray, hop: int,
                                sample_rate: int,
                                freqs: Optional[np.ndarray] = None
                                ) -> Optional[int]:
    """Find the accompaniment loop period in STFT frames.

    Autocorrelation of an energy envelope, peak search between 0.5 s and
    8 s. When freqs (the STFT bin frequencies) is given, the envelope is
    taken over the 40-150 Hz kick band: the kick repeats with the beat and
    the voice lives above it, so the beat's repetition survives even when
    a loud vocal dominates the broadband envelope. Falls back to the
    broadband envelope when the kick band carries no energy.

    The raw autocorrelation is smoothed so a single-frame noise spike
    cannot win. The strongest smoothed peak with at least 3 whole
    repetitions in the audio is returned: that peak is the dominant
    repetition rate of the kick band, and 3+ repetitions are what the
    median background needs to reject the vocal. Returns None when no
    lag reaches the 0.4 absolute threshold.
    """
    def _envelope(band: np.ndarray) -> np.ndarray:
        e = band.sum(axis=0).astype(np.float64)
        return e - e.mean()

    n_frames = mag.shape[1]
    envelope = None
    if freqs is not None:
        kick = mag[(freqs >= 40) & (freqs < 150)]
        if kick.size and float(np.median(kick)) > 1e-9:
            envelope = _envelope(kick)
    if envelope is None:
        envelope = _envelope(mag)

    n = len(envelope)
    min_lag = max(2, int(0.5 * sample_rate / hop))
    max_lag = min(n - 1, int(8.0 * sample_rate / hop))
    if max_lag <= min_lag:
        return None
    corr = np.correlate(envelope, envelope, mode="full")[n - 1:]
    norm = corr[0] if corr[0] > 0 else 1.0
    r = corr / norm
    window = r[min_lag:max_lag + 1]
    if window.max() < 0.4:
        return None
    smooth = np.convolve(window, np.ones(5) / 5.0, mode="same")
    last = len(smooth) - 1
    n_frames = mag.shape[1]
    peaks = [i for i in range(1, last)
             if smooth[i] >= smooth[i - 1] and smooth[i] >= smooth[i + 1]]
    peaks.sort(key=lambda i: smooth[i], reverse=True)
    for i in peaks:
        period = min_lag + i
        if n_frames // period >= 3:
            return period
    return None


def _repeating_background(mag: np.ndarray,
                          period_frames: Optional[int]) -> np.ndarray:
    """Median-aggregated repeating spectrogram, tiled back to full length.

    With a detected period: reshape into whole periods, take the element-wise
    median across periods (the part that repeats in most periods survives;
    the vocal, which sings different notes in each period, does not), tile
    to cover all frames. The period picker guarantees at least 3 periods,
    which is what makes the median robust. Without a detected period: the
    median spectrum over time, the same idea with one degenerate period.
    """
    n_freq, n_frames = mag.shape

    def _tile_median(m: np.ndarray) -> np.ndarray:
        bg = np.median(m, axis=1, keepdims=True)
        return np.repeat(bg, n_frames, axis=1)

    if period_frames is None or period_frames < 2:
        return _tile_median(mag)
    n_seg = n_frames // period_frames
    if n_seg < 2:
        return _tile_median(mag)
    trimmed = mag[:, :n_seg * period_frames]
    segs = trimmed.reshape(n_freq, n_seg, period_frames)
    model = np.median(segs, axis=1)
    tiled = np.tile(model, (1, n_seg + 1))
    return tiled[:, :n_frames]


def _center_mask(z_left: np.ndarray, z_right: np.ndarray) -> np.ndarray:
    """Per-bin centeredness in [0, 1], softly sharpened.

    ratio = mid_power / (mid_power + side_power). Centered content scores
    near 1, hard-panned content near 0. Mono input (identical channels)
    scores exactly 1 everywhere, which correctly reduces the separator to
    the repetition cue alone.
    """
    mid_power = np.abs(z_left + z_right) ** 2
    side_power = np.abs(z_left - z_right) ** 2
    ratio = mid_power / (mid_power + side_power + 1e-12)
    return ratio ** 2


def separate_vocals(audio: np.ndarray, sample_rate: int
                    ) -> Tuple[np.ndarray, np.ndarray]:
    """Split audio into (vocal_estimate, accompaniment_estimate).

    audio: mono (N,) or stereo (2, N). Returns the same layout, sample
    counts preserved exactly. Deterministic: same input, same output.
    """
    stereo, was_mono = _as_stereo(audio)
    n = stereo.shape[1]
    z_left, z_right, hop = _stft_pair(stereo)

    mono_mag = (np.abs(z_left) + np.abs(z_right)) / 2.0
    freqs = np.fft.rfftfreq(_NPERSEG, 1.0 / sample_rate)
    period = estimate_loop_period_frames(mono_mag, hop, sample_rate, freqs)
    background = _repeating_background(mono_mag, period)

    # Foreground: what the mixture has that the repeating background lacks.
    foreground = np.clip((mono_mag - background) / (mono_mag + 1e-9), 0.0, 1.0)
    centered = _center_mask(z_left, z_right)
    vocal_mask = np.clip(centered * foreground, 0.0, 1.0)

    v_left = _istft_trim(vocal_mask * z_left, n)
    v_right = _istft_trim(vocal_mask * z_right, n)
    a_left = _istft_trim((1.0 - vocal_mask) * z_left, n)
    a_right = _istft_trim((1.0 - vocal_mask) * z_right, n)

    if was_mono:
        return (v_left + v_right) / 2.0, (a_left + a_right) / 2.0
    return np.stack([v_left, v_right]), np.stack([a_left, a_right])


def highpass(samples: np.ndarray, sample_rate: int,
             cutoff_hz: float = 120.0, order: int = 4) -> np.ndarray:
    """Zero-phase Butterworth highpass. Used to condition a separated vocal
    before reference analysis: it removes residual kick and bass rumble
    that would otherwise drag the identity vector's spectral centroid down.
    Deterministic."""
    arr = np.asarray(samples, dtype=np.float64)
    sos = signal.butter(order, cutoff_hz, btype="highpass",
                        fs=sample_rate, output="sos")
    return signal.sosfiltfilt(sos, arr)
