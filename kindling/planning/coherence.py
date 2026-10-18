"""Long-form coherence checks (Part 6.5).

Automatic checks: tempo drift and key violations below threshold, lyric
completeness on every test song, motif return, and intentional transitions.
These run in CI; the fixed-suite listening half arrives with Part 17.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from kindling.data import analysis as data_analysis
from kindling.scene.audio_import import estimate_tempo
from kindling.scene.model import scene_to_seconds_map

TEMPO_DRIFT_MAX_BPM = 3.0
KEY_VIOLATIONS_MAX = 1
LYRIC_COMPLETENESS_MIN = 1.0


def _section_audio(audio: np.ndarray, rate: int, start_s: float,
                   end_s: float) -> np.ndarray:
    mono = np.asarray(audio, dtype=float)
    if mono.ndim == 2:
        mono = mono.mean(axis=1)
    return mono[int(start_s * rate):int(end_s * rate)]


def check_tempo_drift(scene: Dict[str, Any], audio: np.ndarray,
                      rate: int) -> Dict[str, Any]:
    smap = scene_to_seconds_map(scene)
    map_bpm = scene["timeline"]["tempo"][0]["bpm"]
    worst = 0.0
    per_section = {}
    for section in scene.get("sections", []):
        bounds = smap.get(section["id"])
        if not bounds:
            continue
        chunk = _section_audio(audio, rate, bounds["start_s"], bounds["end_s"])
        est = estimate_tempo(list(chunk), rate)
        if est["bpm"] and est["confidence"] >= 0.35:
            drift = abs(est["bpm"] - map_bpm)
            worst = max(worst, drift)
            per_section[section["id"]] = round(drift, 2)
    return {"worst_drift_bpm": round(worst, 2), "per_section": per_section,
            "passed": worst <= TEMPO_DRIFT_MAX_BPM}


def check_key_violations(scene: Dict[str, Any], audio: np.ndarray,
                         rate: int) -> Dict[str, Any]:
    smap = scene_to_seconds_map(scene)
    map_key = scene["timeline"]["key"][0]["key"].lower()
    violations = []
    for section in scene.get("sections", []):
        bounds = smap.get(section["id"])
        if not bounds:
            continue
        chunk = _section_audio(audio, rate, bounds["start_s"], bounds["end_s"])
        if len(chunk) < rate:
            continue
        key = data_analysis.estimate_key(chunk, rate)
        if key["confidence"] >= 0.5 and key["value"] and key["value"].lower() != map_key:
            violations.append({"section": section["id"], "map_key": map_key,
                               "estimated": key["value"],
                               "confidence": key["confidence"]})
    return {"violations": violations, "count": len(violations),
            "passed": len(violations) <= KEY_VIOLATIONS_MAX}


def check_lyric_completeness(scene: Dict[str, Any]) -> Dict[str, Any]:
    lines = {ln["id"] for ln in scene.get("lyrics", {}).get("lines", [])}
    referenced = set()
    for vocal in scene.get("vocals", []):
        referenced |= set(vocal.get("lines", []))
    for section in scene.get("sections", []):
        referenced |= set(section.get("lyrics", []))
    missing = sorted(lines - referenced)
    completeness = 1.0 if not lines else 1.0 - len(missing) / len(lines)
    return {"total_lines": len(lines), "missing": missing,
            "completeness": round(completeness, 3),
            "passed": completeness >= LYRIC_COMPLETENESS_MIN}


def check_motif_return(scene: Dict[str, Any]) -> Dict[str, Any]:
    """The planner's motif intervals should recur in the melody after their
    first appearance (motif return and development, Part 6.5)."""
    motifs = scene.get("motifs", [])
    melody = [n["pitch"] for n in scene.get("melody", {}).get("notes", [])]
    if not motifs or len(melody) < 4:
        return {"checked": False, "passed": True, "detail": "no motif or melody"}
    intervals = [b - a for a, b in zip(melody, melody[1:])]
    motif_pitches = motifs[0]["intervals"]
    motif_intervals = [b - a for a, b in zip(motif_pitches, motif_pitches[1:])]
    need = max(2, int(len(motif_intervals) * 0.6))
    hits = 0
    for i in range(len(intervals) - len(motif_intervals) + 1):
        window = intervals[i:i + len(motif_intervals)]
        matches = sum(1 for a, b in zip(window, motif_intervals) if abs(a - b) <= 1)
        if matches >= need:
            hits += 1
    return {"checked": True, "occurrences": hits,
            "passed": hits >= 2,
            "detail": f"motif found {hits} times"}


def check_transitions(scene: Dict[str, Any]) -> Dict[str, Any]:
    """Every section boundary should carry an intentional transition: an
    arrangement change (roles entering or exiting) or an explicit transition
    annotation. Boundaries with neither are warnings, not failures."""
    arrangement = {a["section"]: a for a in scene.get("arrangement", [])}
    sections = scene.get("sections", [])
    unmarked = []
    for i in range(1, len(sections)):
        sid = sections[i]["id"]
        arr = arrangement.get(sid, {})
        transitions = sections[i].get("transitions", [])
        if not arr.get("enters") and not arr.get("exits") and not transitions:
            unmarked.append(sid)
    return {"unmarked_boundaries": unmarked, "passed": True,
            "warnings": [f"{s}: no intentional transition marked" for s in unmarked]}


def coherence_report(scene: Dict[str, Any], audio: np.ndarray,
                     rate: int) -> Dict[str, Any]:
    tempo = check_tempo_drift(scene, audio, rate)
    key = check_key_violations(scene, audio, rate)
    lyrics = check_lyric_completeness(scene)
    motif = check_motif_return(scene)
    transitions = check_transitions(scene)
    checks = {"tempo_drift": tempo, "key_violations": key,
              "lyric_completeness": lyrics, "motif_return": motif,
              "transitions": transitions}
    hard = ["tempo_drift", "key_violations", "lyric_completeness", "motif_return"]
    passed = all(checks[k]["passed"] for k in hard)
    return {"checks": checks, "passed": passed}
