"""Fixed evaluation suite (17.1): frozen, versioned, with a held-out hard set.

Covers genres, languages, tempos, vocal types, song lengths, and prompt
styles. Refreshed on a published schedule WITHOUT leaking into training
(the TestSetGuard from Part 16 enforces this).
"""

from typing import Any, Dict, List

SUITE_VERSION = "1.0.0"
REFRESH_SCHEDULE = "quarterly"


def _prompt(genre: str, tempo: int, language: str, vocal: str,
            length: str, style: str) -> Dict[str, Any]:
    return {"genre": genre, "tempo_bpm": tempo, "language": language,
            "vocal_type": vocal, "length": length, "prompt_style": style,
            "prompt": f"A {length} {genre} song at {tempo} BPM with "
                      f"{vocal} vocals in {language}"}


def build_suite() -> List[Dict[str, Any]]:
    """The frozen suite (17.1)."""
    suite = []
    genres = ["hip-hop", "rock", "electronic", "folk"]
    for genre in genres:
        suite.append(_prompt(genre, 120, "en", "lead", "short", "direct"))
    suite.append(_prompt("hip-hop", 140, "es", "lead", "short", "direct"))
    suite.append(_prompt("rock", 90, "en", "harmony", "medium", "evocative"))
    suite.append(_prompt("electronic", 128, "en", "none", "medium", "direct"))
    suite.append(_prompt("folk", 100, "en", "lead", "long", "story"))
    return suite


def build_held_out() -> List[Dict[str, Any]]:
    """The held-out hard set: unusual combos, never used in training."""
    return [
        _prompt("jazz", 200, "es", "scat", "short", "abstract"),
        _prompt("metal", 180, "en", "growl", "medium", "direct"),
        _prompt("ambient", 60, "en", "none", "long", "evocative"),
    ]


def suite_ids(suite: List[Dict[str, Any]]) -> List[str]:
    return [f"eval-{i:03d}-{p['genre']}-{p['tempo_bpm']}"
            for i, p in enumerate(suite)]
