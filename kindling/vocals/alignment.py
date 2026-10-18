"""Syllable-level lyric alignment (Part 7).

Aligns phonemized syllables to melody notes: one syllable per note in the
common case, melisma when notes outnumber syllables, and explicit
unassigned status when syllables outnumber notes. Nothing is silently
dropped: every syllable ends up aligned, melismatic, or unassigned, with a
confidence.
"""

from __future__ import annotations

from typing import Any, Dict, List

from kindling.vocals.g2p import SUPPORTED_LANGUAGES


def align_line(syllables: List[Dict[str, Any]],
               notes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Align syllables to notes in order.

    syllables: from phonemize(). notes: [{pitch, start_beats,
    duration_beats}]. Returns the alignment plus a confidence and any
    warnings.
    """
    alignment: List[Dict[str, Any]] = []
    warnings: List[str] = []
    n_syl, n_notes = len(syllables), len(notes)

    if n_syl == 0 or n_notes == 0:
        return {"alignment": [], "confidence": 0.0,
                "warnings": ["no syllables or no notes to align"]}

    if n_syl <= n_notes:
        # One syllable per note; surplus notes extend the previous syllable
        # as melisma.
        note_i = 0
        for s_i, syl in enumerate(syllables):
            remaining_syl = n_syl - s_i
            remaining_notes = n_notes - note_i
            take = max(1, remaining_notes - (remaining_syl - 1))
            chord = notes[note_i:note_i + take]
            alignment.append({
                "syllable": syl,
                "notes": chord,
                "start_beats": chord[0]["start_beats"],
                "end_beats": chord[-1]["start_beats"] + chord[-1]["duration_beats"],
                "status": "aligned" if take == 1 else "melisma",
            })
            note_i += take
        confidence = 1.0
    else:
        for n_i, note in enumerate(notes):
            alignment.append({
                "syllable": syllables[n_i],
                "notes": [note],
                "start_beats": note["start_beats"],
                "end_beats": note["start_beats"] + note["duration_beats"],
                "status": "aligned",
            })
        for syl in syllables[n_notes:]:
            alignment.append({"syllable": syl, "notes": [],
                              "start_beats": None, "end_beats": None,
                              "status": "unassigned"})
        warnings.append(f"{n_syl - n_notes} syllable(s) have no note; "
                        "they are marked unassigned, not dropped")
        confidence = round(n_notes / n_syl, 3)

    return {"alignment": alignment, "confidence": confidence, "warnings": warnings}


def align_lyric_line(text: str, notes: List[Dict[str, Any]],
                     language: str = "en") -> Dict[str, Any]:
    """Phonemize one lyric line and align it to notes."""
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"language {language!r} not supported")
    syllables = SUPPORTED_LANGUAGES[language].phonemize(text)
    result = align_line(syllables, notes)
    result["language"] = language
    result["text"] = text
    return result
