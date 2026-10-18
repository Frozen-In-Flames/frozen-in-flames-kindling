"""Virtual instruments (Part 9)."""

from .distill import distill_bass, distill_guitar
from .performance import PerformanceEngine
from .spec import (InstrumentAsset, make_bass_asset, make_guitar_asset,
                   make_keys_asset)
from .synth import StudentBass, StudentGuitar, TeacherBass, TeacherGuitar

__all__ = [
    "InstrumentAsset", "make_guitar_asset", "make_bass_asset",
    "make_keys_asset", "PerformanceEngine",
    "TeacherGuitar", "StudentGuitar", "TeacherBass", "StudentBass",
    "distill_guitar", "distill_bass",
]
