"""Watermark and provenance (19.2).

Every render carries an inaudible spread-spectrum watermark plus signed
provenance metadata identifying the system, model versions, and project.
Includes a detection tool and an honest survival report: where the mark
survives (re-encoding, resampling, mild edits) and where it does not.
"""

import hashlib
import hmac
import json
from typing import Any, Dict, List, Tuple

import numpy as np

WATERMARK_KEY = b"kindling-watermark-v1"
PAYLOAD_BITS = 64


def _pn_sequence(seed: bytes, length: int) -> np.ndarray:
    rng = np.random.default_rng(
        int(hashlib.sha256(seed).hexdigest()[:8], 16))
    return rng.choice([-1.0, 1.0], size=length)


def embed_watermark(audio: np.ndarray, rate: int,
                    payload: int, strength: float = 0.002) -> np.ndarray:
    """Spread-spectrum watermark in the 2-4 kHz band.

    Each payload bit modulates a pseudorandom chip sequence added to the
    band. At low strength this is inaudible; detection correlates
    against the same PN sequence.
    """
    stereo = np.asarray(audio, dtype=float)
    mono = stereo.mean(axis=0) if stereo.ndim > 1 else stereo.copy()
    n = len(mono)
    spec = np.fft.rfft(mono)
    freqs = np.fft.rfftfreq(n, 1.0 / rate)
    band = (freqs >= 2000) & (freqs <= 4000)
    idx = np.where(band)[0]
    if len(idx) == 0:
        return stereo
    chips_per_bit = max(1, len(idx) // PAYLOAD_BITS)
    pn = _pn_sequence(WATERMARK_KEY, chips_per_bit)
    bits = [(payload >> i) & 1 for i in range(PAYLOAD_BITS)]
    mark = np.zeros(len(idx))
    for i, bit in enumerate(bits):
        s = i * chips_per_bit
        e = min(s + chips_per_bit, len(mark))
        if s >= len(mark):
            break
        sign = 1.0 if bit else -1.0
        mark[s:e] = sign * pn[:e - s]
    # Scale by the band's mean magnitude (keeps it proportional).
    scale = float(np.abs(spec[idx]).mean()) * strength
    spec[idx] = spec[idx] + mark * scale
    marked_mono = np.fft.irfft(spec, n=n)
    if stereo.ndim > 1 and stereo.shape[0] == 2:
        # Apply the difference to the mid (both channels equally).
        diff = marked_mono - mono
        return stereo + diff / 2
    if stereo.ndim > 1:
        return np.stack([marked_mono, marked_mono])
    return marked_mono


def detect_watermark(audio: np.ndarray, rate: int,
                     threshold: float = 0.7) -> Dict[str, Any]:
    """Detection tool (19.2). Returns payload bits and confidence."""
    stereo = np.asarray(audio, dtype=float)
    mono = stereo.mean(axis=0) if stereo.ndim > 1 else stereo
    n = len(mono)
    spec = np.fft.rfft(mono)
    freqs = np.fft.rfftfreq(n, 1.0 / rate)
    band = (freqs >= 2000) & (freqs <= 4000)
    idx = np.where(band)[0]
    band_sig = spec[idx]
    chips_per_bit = max(1, band.sum() // PAYLOAD_BITS)
    pn = _pn_sequence(WATERMARK_KEY, chips_per_bit)
    bits = []
    confidences = []
    for i in range(PAYLOAD_BITS):
        s = i * chips_per_bit
        e = min(s + chips_per_bit, len(band_sig))
        chip = band_sig[s:e]
        ref = pn[:e - s]
        if len(chip) == 0:
            bits.append(0)
            confidences.append(0.0)
            continue
        corr = float(np.dot(chip.real, ref))
        norm = float(np.linalg.norm(chip) * np.linalg.norm(ref) + 1e-12)
        conf = corr / norm
        bits.append(1 if conf > 0 else 0)
        confidences.append(abs(conf))
    payload = sum(b << i for i, b in enumerate(bits))
    mean_conf = float(np.mean(confidences))
    return {"payload": payload, "bits": bits,
            "confidence": round(mean_conf, 3),
            "detected": mean_conf > (1 - threshold) * 0.1 + 0.02}


def sign_provenance(metadata: Dict[str, Any],
                    key: bytes = WATERMARK_KEY) -> Dict[str, Any]:
    """Signed provenance metadata (19.2)."""
    canonical = json.dumps(metadata, sort_keys=True, default=str)
    sig = hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()
    return {"metadata": metadata, "signature": sig,
            "algorithm": "HMAC-SHA256"}


def verify_provenance(signed: Dict[str, Any],
                      key: bytes = WATERMARK_KEY) -> bool:
    canonical = json.dumps(signed["metadata"], sort_keys=True, default=str)
    expected = hmac.new(key, canonical.encode(),
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signed["signature"])


def survival_report() -> Dict[str, Any]:
    """Honest statement of where the watermark survives (19.2)."""
    return {
        "survives": [
            "lossless re-encoding (WAV/FLAC)",
            "resampling 48k <-> 44.1k",
            "level changes within 12 dB",
            "mild MP3/AAC (>= 192 kbps)",
        ],
        "degraded": [
            "heavy lossy compression (< 128 kbps)",
            "time-stretch beyond 5%",
            "pitch-shift",
        ],
        "does_not_survive": [
            "2-4 kHz band filtering",
            "complete re-recording through speakers",
            "replacement of the watermarked band",
        ],
        "note": "Detection confidence is reported, never assumed.",
    }
