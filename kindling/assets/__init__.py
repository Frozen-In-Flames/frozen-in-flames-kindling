"""Creative assets (Build Manual Parts 8, 9, 10).

Saved, reusable creative assets captured once and reused: voice characters
(Part 8), virtual instruments (Part 9), and production presets (Part 10).
The kindling you lay down before every song.
"""

from kindling.assets.voice import (
    VOICE_SCHEMA,
    VoiceCharacterStore,
    analyze_reference,
    create_voice_character,
    sufficiency_report,
)
from kindling.assets.separate import highpass, separate_vocals

__all__ = [
    "VOICE_SCHEMA",
    "VoiceCharacterStore",
    "analyze_reference",
    "create_voice_character",
    "highpass",
    "separate_vocals",
    "sufficiency_report",
]
