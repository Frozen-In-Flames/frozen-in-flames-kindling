"""MusicXML import and export (Part 3.6).

Implements the subset of score-partwise MusicXML the scene needs: parts,
measures, and pitched notes with step, alter, and octave. Written with the
standard library only, so there are no new dependencies.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, List

from kindling.scene.model import make_element_meta

DIVISIONS = 480
STEP_TO_SEMI = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
SEMI_TO_STEP = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("D", 1), 4: ("E", 0),
                5: ("F", 0), 6: ("F", 1), 7: ("G", 0), 8: ("G", 1), 9: ("A", 0),
                10: ("A", 1), 11: ("B", 0)}


def midi_to_step_octave(pitch: int) -> tuple:
    step, alter = SEMI_TO_STEP[pitch % 12]
    return step, alter, (pitch // 12) - 1


def step_octave_to_midi(step: str, alter: int, octave: int) -> int:
    return STEP_TO_SEMI[step] + alter + (octave + 1) * 12


def scene_to_musicxml(scene: Dict[str, Any], path: str) -> None:
    """Export scene parts as score-partwise MusicXML (Part 3.6)."""
    root = ET.Element("score-partwise", version="4.0")
    part_list = ET.SubElement(root, "part-list")
    parts = [p for p in scene.get("parts", []) if p.get("notes")]
    if scene.get("melody", {}).get("notes"):
        parts = parts + [{"id": "melody", "notes": scene["melody"]["notes"]}]
    for part in parts:
        score_part = ET.SubElement(part_list, "score-part", id=part["id"])
        ET.SubElement(score_part, "part-name").text = part["id"]

    for part in parts:
        part_el = ET.SubElement(root, "part", id=part["id"])
        notes = sorted(part["notes"], key=lambda n: n["start_beats"])
        if not notes:
            continue
        last_bar = max(int(n["start_beats"] // 4) + 1 for n in notes)
        by_bar: Dict[int, List[Dict[str, Any]]] = {b: [] for b in range(1, last_bar + 1)}
        for note in notes:
            by_bar[int(note["start_beats"] // 4) + 1].append(note)
        for bar in range(1, last_bar + 1):
            measure = ET.SubElement(part_el, "measure", number=str(bar))
            attrs = ET.SubElement(measure, "attributes")
            ET.SubElement(attrs, "divisions").text = str(DIVISIONS)
            cursor = (bar - 1) * 4.0
            for note in sorted(by_bar[bar], key=lambda n: n["start_beats"]):
                gap = note["start_beats"] - cursor
                if gap > 1e-9:
                    rest = ET.SubElement(measure, "note")
                    ET.SubElement(rest, "rest")
                    ET.SubElement(rest, "duration").text = str(int(round(gap * DIVISIONS)))
                    cursor = note["start_beats"]
                note_el = ET.SubElement(measure, "note")
                pitch_el = ET.SubElement(note_el, "pitch")
                step, alter, octave = midi_to_step_octave(note["pitch"])
                ET.SubElement(pitch_el, "step").text = step
                if alter:
                    ET.SubElement(pitch_el, "alter").text = str(alter)
                ET.SubElement(pitch_el, "octave").text = str(octave)
                ET.SubElement(note_el, "duration").text = str(
                    int(round(note["duration_beats"] * DIVISIONS)))
                cursor = note["start_beats"] + note["duration_beats"]

    tree = ET.ElementTree(root)
    ET.indent(tree)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def musicxml_to_scene(path: str, scene_id=None) -> Dict[str, Any]:
    """Import score-partwise MusicXML into a scene (Part 3.6)."""
    from kindling.scene.model import make_scene

    tree = ET.parse(path)
    root = tree.getroot()
    scene = make_scene(scene_id=scene_id, created_by="musicxml-import")
    for part_el in root.findall("part"):
        part_id = part_el.get("id", "part")
        notes = []
        for measure in part_el.findall("measure"):
            bar = int(measure.get("number", "1"))
            divisions = DIVISIONS
            attrs = measure.find("attributes")
            if attrs is not None:
                div_el = attrs.find("divisions")
                if div_el is not None:
                    divisions = int(div_el.text)
            cursor_beats = (bar - 1) * 4.0
            for note_el in measure.findall("note"):
                dur_el = note_el.find("duration")
                duration_beats = (int(dur_el.text) / divisions) if dur_el is not None else 0.0
                pitch_el = note_el.find("pitch")
                if pitch_el is None:
                    cursor_beats += duration_beats
                    continue
                step = pitch_el.findtext("step")
                alter = int(pitch_el.findtext("alter", default="0"))
                octave = int(pitch_el.findtext("octave"))
                notes.append({
                    "pitch": step_octave_to_midi(step, alter, octave),
                    "start_beats": round(cursor_beats, 6),
                    "duration_beats": round(duration_beats, 6),
                    "velocity": 0.8,
                })
                cursor_beats += duration_beats
        if notes:
            scene["parts"].append({
                "id": part_id,
                "role": "imported",
                "notes": notes,
                "articulations": [],
                "dynamics": [],
                "expression": {},
                "meta": make_element_meta(source="imported", confidence=1.0,
                                          realization="symbolic"),
            })
    return scene
