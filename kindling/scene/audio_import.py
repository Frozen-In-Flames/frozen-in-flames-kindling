"""Finished-audio and stem import (Part 3.6).

Finished audio enters the scene through analysis, with confidences (Part 2.1
principle 4: uncertainty is shown). This module does the deterministic part of
that analysis: duration, peak and RMS level, an onset-based tempo estimate
with a confidence, and a per-second energy curve. Structural analysis
(sections, chords, melody) is the job of the reference analyzer (V6) and
preset inference (V10); until those run, imported audio is an audio-level
element, and the scene says so plainly.
"""

from __future__ import annotations

import math
import struct
import wave
from typing import Any, Dict, List, Optional

from kindling.scene.model import make_element_meta


def read_wav_mono(path: str) -> Dict[str, Any]:
    """Read a PCM WAV file into mono float samples in [-1, 1]."""
    with wave.open(path, "rb") as wf:
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        rate = wf.getframerate()
        frames = wf.getnframes()
        raw = wf.readframes(frames)
    if width == 1:
        ints = [(b - 128) / 128.0 for b in raw]
    elif width == 2:
        count = len(raw) // 2
        ints = [v / 32768.0 for v in struct.unpack(f"<{count}h", raw)]
    elif width == 4:
        count = len(raw) // 4
        ints = [v / 2147483648.0 for v in struct.unpack(f"<{count}i", raw)]
    else:
        raise ValueError(f"unsupported sample width: {width}")
    if channels > 1:
        mono = [sum(ints[i * channels:(i + 1) * channels]) / channels
                for i in range(frames)]
    else:
        mono = ints
    return {"samples": mono, "sample_rate": rate, "channels": channels,
            "duration_s": frames / rate if rate else 0.0}


def _onset_envelope(samples: List[float], rate: int,
                    frame_s: float = 0.023) -> List[float]:
    frame = max(64, int(rate * frame_s))
    hop = frame // 2
    prev = 0.0
    envelope = []
    for start in range(0, len(samples) - frame, hop):
        energy = sum(s * s for s in samples[start:start + frame]) / frame
        flux = max(0.0, energy - prev)
        envelope.append(flux)
        prev = energy
    return envelope


def estimate_tempo(samples: List[float], rate: int) -> Dict[str, Any]:
    """Tempo from onset-envelope autocorrelation over 60 to 200 BPM.

    Returns {"bpm": float or None, "confidence": float}. Confidence is the
    autocorrelation peak height relative to the mean, scaled to [0, 1].
    A flat or noisy signal yields low confidence, and the caller must show
    that instead of guessing (principle 4).
    """
    envelope = _onset_envelope(samples, rate)
    if len(envelope) < 64 or max(envelope) <= 0:
        return {"bpm": None, "confidence": 0.0}
    hop_s = (max(64, int(rate * 0.023)) // 2) / rate
    mean = sum(envelope) / len(envelope)
    normed = [e - mean for e in envelope]
    denom = sum(e * e for e in normed) or 1.0

    min_lag = max(1, int(round(60.0 / 200 / hop_s)))
    max_lag = min(len(normed) // 2, int(round(60.0 / 60 / hop_s)))
    corrs = {}
    for lag in range(min_lag, max_lag + 1):
        corr = sum(normed[i] * normed[i + lag] for i in range(len(normed) - lag)) / denom
        corrs[lag] = corr
    if not corrs:
        return {"bpm": None, "confidence": 0.0}
    peak = max(corrs.values())
    # Octave correction: among lags with a strong peak, prefer the shortest
    # (fastest tempo). A click every beat also correlates every two beats.
    strong = [lag for lag, corr in corrs.items() if corr >= 0.6 * peak]
    best_lag = min(strong)
    best_corr = corrs[best_lag]
    bpm = 60.0 / (best_lag * hop_s)
    confidence = max(0.0, min(1.0, best_corr * 4.0))
    return {"bpm": round(bpm, 2), "confidence": round(confidence, 3)}


def analyze_audio(path: str) -> Dict[str, Any]:
    """Deterministic analysis of a finished recording, with confidences."""
    audio = read_wav_mono(path)
    samples = audio["samples"]
    peak = max((abs(s) for s in samples), default=0.0)
    rms = math.sqrt(sum(s * s for s in samples) / len(samples)) if samples else 0.0
    tempo = estimate_tempo(samples, audio["sample_rate"])
    per_second = []
    rate = audio["sample_rate"]
    for sec in range(int(audio["duration_s"]) + 1):
        chunk = samples[sec * rate:(sec + 1) * rate]
        if chunk:
            per_second.append(round(math.sqrt(sum(s * s for s in chunk) / len(chunk)), 4))
    return {
        "path": path,
        "duration_s": round(audio["duration_s"], 3),
        "sample_rate": audio["sample_rate"],
        "channels": audio["channels"],
        "peak": round(peak, 4),
        "rms": round(rms, 4),
        "tempo_estimate": tempo,
        "energy_curve": per_second,
    }


def import_audio_as_scene(path: str, title: str = "imported",
                          scene_id=None) -> Dict[str, Any]:
    """Import finished audio as an audio-realization scene element.

    The scene carries the analysis with confidences and marks structural
    content (sections, harmony, melody) as not yet analyzed, with a warning,
    instead of inventing it.
    """
    from kindling.scene.model import make_scene

    analysis = analyze_audio(path)
    scene = make_scene(scene_id=scene_id, created_by="audio-import")
    tempo = analysis["tempo_estimate"]
    if tempo["bpm"] and tempo["confidence"] >= 0.35:
        scene["timeline"]["tempo"] = [{"bar": 1, "bpm": tempo["bpm"]}]
    scene["sections"].append({
        "id": "sec_full",
        "type": "custom",
        "bars": [1, max(1, int(analysis["duration_s"] / 2))],
        "description": title,
        "meta": make_element_meta(source="imported",
                                  confidence=tempo["confidence"],
                                  realization="audio"),
    })
    scene["melody"] = {
        "notes": [],
        "contour": None,
        "audio_ref": path,
        "analysis": analysis,
        "warning": ("Structural analysis (sections, harmony, melody) not yet "
                    "run. See the reference analyzer (V6) and preset "
                    "inference (V10)."),
        "meta": make_element_meta(source="imported", confidence=0.5,
                                  realization="audio"),
    }
    return scene


def import_stems_as_scene(paths: List[str], scene_id=None) -> Dict[str, Any]:
    """One part per stem, each at audio realization with its own analysis."""
    from kindling.scene.model import make_scene

    scene = make_scene(scene_id=scene_id, created_by="stem-import")
    for index, path in enumerate(paths):
        analysis = analyze_audio(path)
        scene["parts"].append({
            "id": f"stem_{index}",
            "role": "stem",
            "audio_ref": path,
            "analysis": analysis,
            "notes": [],
            "articulations": [],
            "dynamics": [],
            "expression": {},
            "meta": make_element_meta(source="imported", confidence=0.9,
                                      realization="audio"),
        })
    return scene
