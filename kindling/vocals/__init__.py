"""Vocals and lyrics (Build Manual Part 7).

Vocals are the hardest quality challenge, so they are their own system:
syllable-level lyric alignment with per-language pronunciation, line-level
regeneration, expressive controls, automatic intelligibility reporting, and
explicit multilingual support. The reference implementations are
deterministic and rule-driven; learned models (neural G2P, singing
synthesis, ASR) plug into the same interfaces.
"""

from kindling.vocals.g2p import SUPPORTED_LANGUAGES, phonemize
from kindling.vocals.controls import default_performance, validate_performance
from kindling.vocals.alignment import align_line
from kindling.vocals.renderer import ReferenceVocalRenderer
from kindling.vocals.intelligibility import (
    IntelligibilityReport,
    word_error_rate,
)

__all__ = [
    "SUPPORTED_LANGUAGES",
    "phonemize",
    "default_performance",
    "validate_performance",
    "align_line",
    "ReferenceVocalRenderer",
    "IntelligibilityReport",
    "word_error_rate",
]
