"""Deterministic audio analysis for the data pipeline (Part 4.1).

Everything here is classical DSP with numpy, no trained models. Each derived
label carries a confidence and the method that produced it. Where a learned
model is the right tool (lyric transcription, true source separation,
instrument classification), this module provides the interface and a
reference implementation whose limits are documented, never a faked result.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from kindling.data.record import label
from kindling.scene.audio_import import estimate_tempo

KRUMANSHL_MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
KRUMANSHL_MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def chroma_frames(samples: np.ndarray, rate: int,
                  frame_s: float = 0.093) -> Tuple[np.ndarray, float]:
    """Pitch-class energy per frame, normalized per frame."""
    frame = max(256, int(rate * frame_s))
    hop = frame // 2
    window = np.hanning(frame)
    freqs = np.fft.rfftfreq(frame, 1.0 / rate)
    valid = (freqs >= 55.0) & (freqs <= 2093.0)
    pcs = np.mod(np.round(69 + 12 * np.log2(np.maximum(freqs[valid], 1e-9) / 440.0)).astype(int), 12)
    chromas = []
    for start in range(0, len(samples) - frame, hop):
        mag = np.abs(np.fft.rfft(samples[start:start + frame] * window))[valid]
        energy = mag ** 2
        chroma = np.bincount(pcs, weights=energy, minlength=12)
        total = chroma.sum()
        chromas.append(chroma / total if total > 0 else chroma)
    return np.array(chromas), hop / rate


def estimate_key(samples: np.ndarray, rate: int) -> Dict[str, Any]:
    """Key via Krumhansl profile correlation. Returns value + confidence."""
    chromas, _ = chroma_frames(samples, rate)
    if len(chromas) == 0:
        return label(None, 0.0, "krumhansl")
    mean = chromas.mean(axis=0)
    best: Optional[Tuple[str, float]] = None
    for root in range(12):
        for mode, profile in (("major", KRUMANSHL_MAJOR), ("minor", KRUMANSHL_MINOR)):
            rotated = np.roll(profile, root)
            corr = float(np.corrcoef(mean, rotated)[0, 1])
            if best is None or corr > best[1]:
                best = (f"{PITCH_NAMES[root]} {mode}", corr)
    name, corr = best  # type: ignore[misc]
    confidence = max(0.0, min(1.0, (corr - 0.5) * 2.0)) if not math.isnan(corr) else 0.0
    return label(name, round(confidence, 3), "krumhansl")


def _chord_templates() -> Dict[str, np.ndarray]:
    templates = {}
    for root in range(12):
        for suffix, intervals in (("", (0, 4, 7)), ("m", (0, 3, 7))):
            vec = np.zeros(12)
            for iv in intervals:
                vec[(root + iv) % 12] = 1.0
            templates[f"{PITCH_NAMES[root]}{suffix}"] = vec / vec.sum()
    return templates


CHORD_TEMPLATES = _chord_templates()


def estimate_chords(samples: np.ndarray, rate: int,
                    window_s: float = 1.0) -> Dict[str, Any]:
    """Chord per window by template match. Confidence is the winner's margin."""
    chromas, hop_s = chroma_frames(samples, rate)
    if len(chromas) == 0:
        return label([], 0.0, "chroma-template")
    per_window = max(1, int(round(window_s / hop_s)))
    names = list(CHORD_TEMPLATES.keys())
    matrix = np.stack([CHORD_TEMPLATES[n] for n in names])
    chords = []
    confs = []
    for start in range(0, len(chromas), per_window):
        mean = chromas[start:start + per_window].mean(axis=0)
        if mean.sum() == 0:
            continue
        scores = matrix @ mean
        order = np.argsort(scores)[::-1]
        winner = names[int(order[0])]
        margin = float(scores[order[0]] - scores[order[1]])
        chords.append({"time_s": round(start * hop_s, 2), "chord": winner})
        confs.append(margin)
    confidence = round(float(np.mean(confs)) * 3.0, 3) if confs else 0.0
    confidence = max(0.0, min(1.0, confidence))
    return label(chords, confidence, "chroma-template")


def estimate_sections(samples: np.ndarray, rate: int) -> Dict[str, Any]:
    """Section boundaries from chroma novelty peaks."""
    chromas, hop_s = chroma_frames(samples, rate, frame_s=0.186)
    if len(chromas) < 8:
        return label([], 0.0, "chroma-novelty")
    diffs = np.linalg.norm(np.diff(chromas, axis=0), axis=1)
    threshold = diffs.mean() + diffs.std()
    boundaries = [0.0]
    for i in range(1, len(diffs) - 1):
        if diffs[i] > threshold and diffs[i] >= diffs[i - 1] and diffs[i] >= diffs[i + 1]:
            boundaries.append(round(i * hop_s, 2))
    boundaries.append(round(len(chromas) * hop_s, 2))
    boundaries = sorted(set(boundaries))
    sections = [{"id": f"sec_{i}", "start_s": boundaries[i], "end_s": boundaries[i + 1]}
                for i in range(len(boundaries) - 1)]
    peak_ratio = float((diffs > threshold).mean())
    confidence = round(max(0.0, min(1.0, 1.0 - peak_ratio * 4.0)), 3)
    return label(sections, confidence, "chroma-novelty")


def energy_curve(samples: np.ndarray, rate: int) -> List[float]:
    per_second = []
    for sec in range(int(len(samples) / rate) + 1):
        chunk = samples[sec * rate:(sec + 1) * rate]
        if len(chunk):
            per_second.append(round(float(np.sqrt(np.mean(chunk ** 2))), 4))
    return per_second


def approximate_loudness_dbfs(samples: np.ndarray) -> float:
    """RMS-based loudness, approximate. Part 13 implements BS.1770 properly;
    the pipeline records this as a processing label, not a master value."""
    rms = float(np.sqrt(np.mean(samples ** 2))) if len(samples) else 0.0
    return round(20 * math.log10(rms + 1e-12), 2)


def heuristic_instrument_role(samples: np.ndarray, rate: int) -> Dict[str, Any]:
    """Spectral heuristic for the instrument role. This is a placeholder with
    deliberately low confidence until a trained classifier exists; the label
    stays in the record, marked, per Part 4.3."""
    if len(samples) < rate:
        return label("unknown", 0.1, "heuristic-spectral")
    spec = np.abs(np.fft.rfft(samples[:rate] * np.hanning(min(rate, len(samples)))))
    freqs = np.fft.rfftfreq(min(rate, len(samples)), 1.0 / rate)
    centroid = float((freqs * spec).sum() / (spec.sum() + 1e-12))
    zcr = float(((samples[:-1] * samples[1:]) < 0).mean())
    if centroid < 300:
        guess = "bass"
    elif centroid > 4000 and zcr > 0.15:
        guess = "drums"
    elif 300 <= centroid <= 1200:
        guess = "vocal"
    else:
        guess = "other"
    return label(guess, 0.3, "heuristic-spectral")


def separate_center_stereo(left: np.ndarray, right: np.ndarray) -> Dict[str, np.ndarray]:
    """Reference stem separation: classical mid/side. The mid channel is
    returned as the center estimate (often vocal-forward), the sides as the
    remainder. Documented limit: this is not learned source separation; the
    interface accepts a learned separator later. The original mix is always
    kept alongside."""
    mid = (left + right) / 2.0
    side = (left - right) / 2.0
    return {"center_estimate": mid, "sides": side, "mix": (left + right) / 2.0}


def _band_onsets(samples: np.ndarray, rate: int, lo: float, hi: float) -> List[float]:
    frame = 2048
    hop = 512
    freqs = np.fft.rfftfreq(frame, 1.0 / rate)
    mask = (freqs >= lo) & (freqs <= hi)
    window = np.hanning(frame)
    fluxes = []
    prev = 0.0
    for start in range(0, len(samples) - frame, hop):
        mag = np.abs(np.fft.rfft(samples[start:start + frame] * window))[mask]
        energy = float((mag ** 2).sum())
        fluxes.append(max(0.0, energy - prev))
        prev = energy
    fluxes = np.array(fluxes)
    if fluxes.max() <= 0:
        return []
    threshold = fluxes.mean() + fluxes.std()
    onsets = []
    for i in range(1, len(fluxes) - 1):
        if fluxes[i] > threshold and fluxes[i] >= fluxes[i - 1] and fluxes[i] >= fluxes[i + 1]:
            onsets.append(round(i * hop / rate, 3))
    return onsets


def align_syllables_to_vocal_onsets(samples: np.ndarray, rate: int,
                                    syllables: List[str]) -> Dict[str, Any]:
    """Reference lyric aligner for caller-provided transcripts.

    Detects onsets in the vocal band (300 to 3400 Hz) and assigns syllables
    to the clearest onsets in order. This aligns a known lyric line; it does
    not transcribe. Transcription needs an acoustic model (interface in
    kindling.interfaces is honored by this module's signature; the learned
    transcriber plugs in here).
    """
    onsets = _band_onsets(np.asarray(samples, dtype=float), rate, 300.0, 3400.0)
    aligned = []
    for i, syllable in enumerate(syllables):
        if i < len(onsets):
            aligned.append({"syllable": syllable, "time_s": onsets[i], "status": "aligned"})
        else:
            aligned.append({"syllable": syllable, "time_s": None, "status": "unaligned"})
    n_aligned = sum(1 for a in aligned if a["status"] == "aligned")
    confidence = round(n_aligned / len(syllables), 3) if syllables else 0.0
    return label(aligned, confidence, "vocal-band-onset-align")


def analyze_track(samples: List[float], rate: int,
                  processing_versions: Optional[Dict[str, str]] = None) -> Dict[str, Dict[str, Any]]:
    """Run the full deterministic analysis for one track. Returns labels."""
    arr = np.asarray(samples, dtype=float)
    tempo = estimate_tempo(list(arr), rate)
    return {
        "duration_s": label(round(len(arr) / rate, 3), 1.0, "header"),
        "sample_rate": label(rate, 1.0, "header"),
        "tempo": label(tempo["bpm"], tempo["confidence"], "onset-autocorrelation"),
        "key": estimate_key(arr, rate),
        "chords": estimate_chords(arr, rate),
        "sections": estimate_sections(arr, rate),
        "energy_curve": label(energy_curve(arr, rate), 0.9, "rms"),
        "loudness_dbfs": label(approximate_loudness_dbfs(arr), 0.7, "rms-approx"),
        "instrument_role": heuristic_instrument_role(arr, rate),
    }
