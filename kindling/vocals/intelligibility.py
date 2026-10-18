"""Intelligibility reporting (Part 7).

The manual requires automatic intelligibility reporting with ASR on isolated
rendered vocals, flagging lines below threshold. This module ships three
honest pieces:

1. word_error_rate: the real WER computation (edit distance on words).
2. TranscriptionModel: the interface a learned ASR model plugs into. The
   full WER acceptance path is: render line, transcribe with the model,
   compute WER against the lyric text.
3. ReferenceIntelligibility: deterministic proxy checks that ARE measurable
   without an ASR model (syllable onset count vs expected, voicing energy
   where vowels should be). It is labeled a proxy everywhere, and it flags
   the reference renderer's output, which is the system working as intended.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

import numpy as np

INTELLIGIBILITY_THRESHOLD = 0.6


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Word error rate: (substitutions + deletions + insertions) / words."""
    ref = reference.lower().split()
    hyp = hypothesis.lower().split()
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, rw in enumerate(ref, 1):
        cur = [i]
        for j, hw in enumerate(hyp, 1):
            cost = 0 if rw == hw else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1] / len(ref)


class TranscriptionModel(ABC):
    """Interface for ASR on isolated rendered vocals (Part 7)."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        pass

    @abstractmethod
    def transcribe(self, audio: np.ndarray, sample_rate: int,
                   language: str) -> str:
        """Return the hypothesized lyric text."""


def wer_report(expected_text: str, asr: TranscriptionModel,
               audio: np.ndarray, sample_rate: int,
               language: str) -> Dict[str, Any]:
    """The real acceptance path: transcribe, then score. Needs a
    TranscriptionModel; without one this raises instead of inventing a
    transcript."""
    hypothesis = asr.transcribe(np.asarray(audio), sample_rate, language)
    wer = word_error_rate(expected_text, hypothesis)
    threshold = 0.25  # Part 1 threshold placeholder; targets.yaml owns it
    return {"expected": expected_text, "hypothesis": hypothesis,
            "wer": round(wer, 3), "threshold": threshold,
            "passed": wer <= threshold, "method": f"asr:{asr.model_id}"}


def _vocal_band_onsets(samples: np.ndarray, rate: int) -> List[float]:
    mono = np.asarray(samples, dtype=float)
    if mono.ndim == 2:
        mono = mono.mean(axis=1)
    frame, hop = 2048, 512
    freqs = np.fft.rfftfreq(frame, 1.0 / rate)
    mask = (freqs >= 300) & (freqs <= 3400)
    window = np.hanning(frame)
    fluxes = []
    prev = 0.0
    for start in range(0, len(mono) - frame, hop):
        mag = np.abs(np.fft.rfft(mono[start:start + frame] * window))[mask]
        energy = float((mag ** 2).sum())
        fluxes.append(max(0.0, energy - prev))
        prev = energy
    fluxes = np.array(fluxes)
    if fluxes.max() <= 0:
        return []
    threshold = fluxes.mean() + 0.5 * fluxes.std()
    return [round(i * hop / rate, 3) for i in range(1, len(fluxes) - 1)
            if fluxes[i] > threshold and fluxes[i] >= fluxes[i - 1]
            and fluxes[i] >= fluxes[i + 1]]


def _voicing_ratio(samples: np.ndarray, rate: int) -> float:
    """Fraction of frames with strong periodicity (vowel-like voicing)."""
    mono = np.asarray(samples, dtype=float)
    if mono.ndim == 2:
        mono = mono.mean(axis=1)
    frame = int(rate * 0.03)
    voiced = 0
    total = 0
    for start in range(0, len(mono) - frame, frame):
        chunk = mono[start:start + frame]
        if np.sqrt(np.mean(chunk ** 2)) < 0.02:
            continue
        total += 1
        chunk = chunk - chunk.mean()
        corr = np.correlate(chunk, chunk, mode="full")[len(chunk) - 1:]
        corr = corr / (corr[0] + 1e-12)
        lo, hi = int(rate / 400), int(rate / 70)
        if hi < len(corr) and corr[lo:hi].max() > 0.55:
            voiced += 1
    return voiced / total if total else 0.0


class ReferenceIntelligibility:
    """Proxy intelligibility: no ASR model, no fake transcript.

    Measures (a) whether the expected number of syllable onsets happened in
    the vocal band, and (b) whether vowel regions carry voicing. Flags lines
    below threshold. Every report states it is a proxy.
    """

    def __init__(self, threshold: float = INTELLIGIBILITY_THRESHOLD):
        self.threshold = threshold

    def check(self, audio: np.ndarray, sample_rate: int,
              expected_syllables: int) -> Dict[str, Any]:
        onsets = _vocal_band_onsets(audio, sample_rate)
        if expected_syllables > 0:
            onset_score = min(1.0, len(onsets) / expected_syllables)
            if len(onsets) > expected_syllables * 2:
                onset_score = max(0.0, 1.0 - (len(onsets) / expected_syllables - 2) / 4)
        else:
            onset_score = 1.0 if not onsets else 0.0
        voicing = _voicing_ratio(audio, sample_rate)
        overall = round(0.5 * onset_score + 0.5 * voicing, 3)
        return {
            "method": "proxy (no ASR model)",
            "expected_syllables": expected_syllables,
            "detected_onsets": len(onsets),
            "onset_score": round(onset_score, 3),
            "voicing_ratio": round(voicing, 3),
            "overall": overall,
            "threshold": self.threshold,
            "flagged": overall < self.threshold,
            "note": ("Proxy scores only. True word error rate needs a "
                     "TranscriptionModel; see wer_report()."),
        }


class IntelligibilityReport:
    """Convenience wrapper: proxy check plus optional ASR WER path."""

    def __init__(self, asr: TranscriptionModel = None,
                 threshold: float = INTELLIGIBILITY_THRESHOLD):
        self.asr = asr
        self.proxy = ReferenceIntelligibility(threshold=threshold)

    def check_line(self, audio: np.ndarray, sample_rate: int,
                   expected_text: str, expected_syllables: int,
                   language: str = "en") -> Dict[str, Any]:
        report: Dict[str, Any] = {
            "proxy": self.proxy.check(audio, sample_rate, expected_syllables)}
        if self.asr is not None:
            report["wer"] = wer_report(expected_text, self.asr, audio,
                                       sample_rate, language)
        else:
            report["wer"] = {"status": "no-asr-model",
                             "note": "plug a TranscriptionModel in for true WER"}
        return report
