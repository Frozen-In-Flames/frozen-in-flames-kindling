"""Composition planner (Part 6.2).

Proposes form, harmony, motifs, energy curve, and arrangement, conditioned
on the scene, assets, and any selected profile context. Offers alternatives
on request and respects locked elements: a locked element is never changed
by the planner.

The reference implementation is theory-driven and deterministic. Harmony
comes from functional progressions per section type; motifs are interval
patterns on the song's scale; the energy curve follows section archetypes;
arrangement assigns instrument roles per section with entrances and exits.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from kindling.interfaces import CompositionPlanner as CompositionPlannerABC
from kindling.scene.model import make_element_meta

# Functional progressions as scale degrees, per section type and mode.
PROGRESSIONS = {
    "major": {
        "verse": [[1, 5, 6, 4], [6, 4, 1, 5], [1, 4, 6, 5]],
        "pre-chorus": [[4, 5], [2, 5], [6, 4, 5]],
        "chorus": [[1, 5, 6, 4], [6, 4, 1, 5], [1, 4, 1, 5]],
        "bridge": [[2, 5, 1], [6, 2, 5, 1], [4, 1, 6, 5]],
        "intro": [[1, 5, 6, 4], [1, 4]],
        "outro": [[1, 5, 6, 4], [6, 4, 1]],
    },
    "minor": {
        "verse": [[1, 6, 3, 7], [1, 7, 6, 7], [1, 4, 7, 3]],
        "pre-chorus": [[6, 7], [4, 7], [2, 7]],
        "chorus": [[1, 6, 3, 7], [1, 7, 3, 6], [6, 7, 1, 1]],
        "bridge": [[4, 7, 3, 6], [1, 4, 7, 7], [2, 7, 1]],
        "intro": [[1, 6, 3, 7], [1, 7]],
        "outro": [[1, 6, 3, 7], [6, 7, 1]],
    },
}

_MAJOR_SCALE = [0, 2, 4, 5, 7, 9, 11]
_MINOR_SCALE = [0, 2, 3, 5, 7, 8, 10]
_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _parse_key(key: str) -> tuple:
    parts = key.strip().split()
    name = parts[0] if parts else "C"
    mode = parts[1].lower() if len(parts) > 1 else "major"
    mode = "minor" if mode.startswith("min") else "major"
    base = _NOTE_NAMES.index(name[0].upper() + name[1:]) if name[0].upper() + name[1:] in _NOTE_NAMES else 0
    return base, mode


def _degree_to_chord(root_pc: int, mode: str, degree: int) -> str:
    scale = _MAJOR_SCALE if mode == "major" else _MINOR_SCALE
    chord_root = (root_pc + scale[(degree - 1) % 7]) % 12
    name = _NOTE_NAMES[chord_root]
    is_minor_degree = mode == "major" and degree in (2, 3, 6)
    is_major_degree = mode == "minor" and degree in (3, 6, 7)
    if is_minor_degree or (mode == "minor" and degree in (1, 4, 5)):
        name += "m"
    elif is_major_degree:
        pass
    return name


def progression_for(key: str, section_type: str, variant: int = 0) -> List[str]:
    """A chord progression for a section: real functional harmony."""
    root_pc, mode = _parse_key(key)
    options = PROGRESSIONS[mode].get(section_type, PROGRESSIONS[mode]["verse"])
    degrees = options[variant % len(options)]
    return [_degree_to_chord(root_pc, mode, d) for d in degrees]


def motif_for(key: str, variant: int = 0) -> List[int]:
    """A melodic motif as scale-degree steps. Small, singable, reusable:
    the coherence checker looks for its return later in the song."""
    root_pc, mode = _parse_key(key)
    scale = _MAJOR_SCALE if mode == "major" else _MINOR_SCALE
    patterns = [
        [0, 2, 4, 2, 0],
        [4, 2, 0, -2, 0],
        [0, 0, 4, 2, 0],
        [7, 4, 2, 0, -2],
    ]
    steps = patterns[variant % len(patterns)]
    return [root_pc + scale[((s % 7) + 7) % 7] + 12 * (1 if s >= 0 else 0) for s in steps]


def energy_curve_for(sections: List[Dict[str, Any]], lift: float = 0.0) -> List[float]:
    archetype = {"intro": 0.2, "verse": 0.35, "pre-chorus": 0.55,
                 "chorus": 0.8, "bridge": 0.6, "outro": 0.25}
    return [round(min(1.0, max(0.05, archetype.get(s.get("type", "verse"), 0.5) + lift)), 2)
            for s in sections]


def arrangement_for(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Instrument roles per section, with entrances and exits."""
    plan = []
    for section in sections:
        stype = section.get("type", "verse")
        energy = section.get("energy", 0.5)
        roles = ["drums", "bass"]
        if stype in ("verse", "pre-chorus", "chorus", "bridge"):
            roles.append("keys")
        if energy >= 0.5:
            roles.append("guitar")
        if energy >= 0.7:
            roles += ["pad", "percussion"]
        if stype in ("verse", "chorus", "bridge"):
            roles.append("lead_vocal")
        if stype == "chorus" and energy >= 0.75:
            roles.append("vocal_double")
        plan.append({"section": section["id"], "roles": roles,
                     "enters": roles, "exits": []})
    for i in range(1, len(plan)):
        prev = set(plan[i - 1]["roles"])
        cur = set(plan[i]["roles"])
        plan[i]["enters"] = sorted(cur - prev)
        plan[i]["exits"] = sorted(prev - cur)
    return plan


def _is_locked(element: Dict[str, Any]) -> bool:
    return bool((element.get("meta") or {}).get("locked", False))


class ReferencePlanner(CompositionPlannerABC):
    @property
    def component_name(self) -> str:
        return "Composition planner"

    @property
    def supported_tiers(self) -> List[str]:
        return ["draft", "studio", "hosted"]

    def plan(self, scene: Dict[str, Any],
             profile_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Fill harmony, motifs, energy, and arrangement. Locked elements are
        never touched. Returns the planned scene plus a change list."""
        scene = copy.deepcopy(scene)
        key = scene["timeline"]["key"][0]["key"]
        changes: List[str] = []
        sections = scene.get("sections", [])

        for i, section in enumerate(sections):
            if _is_locked(section):
                continue
            stype = section.get("type", "verse")
            chords = progression_for(key, stype, variant=i % 3)
            first_bar = section["bars"][0]
            harmony = {"section": section["id"],
                       "chords": [{"bar": first_bar + b, "chord": c, "beats": 4}
                                  for b, c in enumerate(chords)],
                       "meta": make_element_meta(source="planner", confidence=0.8,
                                                 realization="symbolic")}
            scene.setdefault("harmony", [])
            scene["harmony"] = [h for h in scene["harmony"] if h.get("section") != section["id"]]
            scene["harmony"].append(harmony)
            changes.append(f"harmony for {section['id']}: {' - '.join(chords)}")

        energies = energy_curve_for(sections)
        for section, energy in zip(sections, energies):
            if _is_locked(section):
                continue
            if abs(section.get("energy", 0.5) - energy) > 0.01:
                changes.append(f"{section['id']}: energy {section.get('energy')} -> {energy}")
                section["energy"] = energy

        motif = motif_for(key)
        scene.setdefault("motifs", []).append({
            "id": "motif_1", "intervals": motif,
            "meta": make_element_meta(source="planner", confidence=0.7,
                                      realization="symbolic"),
        })
        changes.append(f"motif_1: scale steps {motif}")

        arrangement = arrangement_for(sections)
        scene["arrangement"] = arrangement
        changes.append(f"arrangement: {len(arrangement)} sections planned")

        if profile_context:
            changes.append("profile context noted; v1 planner reads energy bias only")
            bias = profile_context.get("energy_bias", 0.0)
            if bias:
                for section in sections:
                    if not _is_locked(section):
                        section["energy"] = round(min(1.0, max(0.05, section["energy"] + bias)), 2)

        return {"scene": scene, "changes": changes}

    def alternatives(self, scene: Dict[str, Any], element: str,
                     count: int = 3) -> List[Dict[str, Any]]:
        """Offer alternatives for one element: harmony, energy, or motif."""
        key = scene["timeline"]["key"][0]["key"]
        sections = scene.get("sections", [])
        results = []
        for variant in range(count):
            if element == "harmony":
                results.append({
                    "element": element, "variant": variant,
                    "progressions": {s["id"]: progression_for(key, s.get("type", "verse"), variant)
                                     for s in sections},
                })
            elif element == "energy":
                lift = (variant - count // 2) * 0.1
                results.append({
                    "element": element, "variant": variant,
                    "energies": {s["id"]: e for s, e in
                                 zip(sections, energy_curve_for(sections, lift))},
                })
            elif element == "motif":
                results.append({"element": element, "variant": variant,
                                "motif": motif_for(key, variant)})
            else:
                raise ValueError(f"no alternatives for element {element!r}")
        return results
