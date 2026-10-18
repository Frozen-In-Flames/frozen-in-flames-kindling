"""Line-level regeneration (Part 7).

Change a line, realign it, and re-sing only that line while neighboring
lines keep their audio. The contract: the returned scene carries the new
text and alignment, the returned audio covers exactly the line's time range,
and every other line's audio is provably untouched (the caller re-renders
only what changed; Part 12 generalizes this into the editing engine).
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List

from kindling.vocals.alignment import align_lyric_line


def regenerate_line(scene: Dict[str, Any], vocal_part_id: str, line_id: str,
                    new_text: str, renderer, language: str = "en",
                    seed: int = 0) -> Dict[str, Any]:
    """Re-sing one lyric line.

    Requires vocal["line_notes"][line_id]: the notes the line is sung on
    (maintained by the timeline editor). Returns the updated scene, the new
    line audio, its time range in seconds, and the ids of lines whose audio
    is unchanged.
    """
    scene = copy.deepcopy(scene)

    vocal = next((v for v in scene.get("vocals", []) if v["id"] == vocal_part_id), None)
    if vocal is None:
        raise KeyError(f"no vocal part {vocal_part_id!r}")
    line_notes = (vocal.get("line_notes") or {}).get(line_id)
    if not line_notes:
        raise KeyError(f"vocal {vocal_part_id!r} has no notes for line {line_id!r}; "
                       "the timeline editor maintains line_notes")

    line = next((ln for ln in scene.get("lyrics", {}).get("lines", [])
                 if ln["id"] == line_id), None)
    if line is None:
        raise KeyError(f"no lyric line {line_id!r}")

    aligned = align_lyric_line(new_text, line_notes, language=language)
    bpm = scene["timeline"]["tempo"][0]["bpm"]
    lyric_line = dict(aligned)
    lyric_line["bpm"] = bpm

    rendered = renderer.render_line(
        (vocal.get("voice") or {}).get("id", "voice_unknown"),
        lyric_line,
        vocal.get("performance", {}),
        seed,
    )

    line["text"] = new_text
    line["language"] = language
    vocal.setdefault("line_alignments", {})[line_id] = aligned["alignment"]
    vocal.setdefault("line_warnings", {})[line_id] = aligned["warnings"]

    beat_s = 60.0 / bpm
    starts = [a["start_beats"] for a in aligned["alignment"] if a["start_beats"] is not None]
    ends = [a["end_beats"] for a in aligned["alignment"] if a["end_beats"] is not None]
    start_s = min(starts) * beat_s if starts else 0.0
    end_s = max(ends) * beat_s if ends else 0.0

    other_lines = [ln["id"] for ln in scene.get("lyrics", {}).get("lines", [])
                   if ln["id"] != line_id]

    return {
        "scene": scene,
        "line_audio": rendered["audio"],
        "start_s": round(start_s, 3),
        "end_s": round(end_s, 3),
        "regenerated_line": line_id,
        "unchanged_lines": other_lines,
        "alignment_warnings": aligned["warnings"],
        "render_warnings": rendered["metadata"]["warnings"],
    }
