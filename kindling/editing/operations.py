"""Edit operations (12.1). Each takes a scene and returns a new scene
plus the list of changed elements. Deterministic given the seed.
"""

import copy
from typing import Any, Dict, List, Tuple

import numpy as np

from .contract import EditRequest


def _beats_to_seconds(beats: float, bpm: float) -> float:
    return beats * 60.0 / bpm


def _get_bpm(scene: Dict[str, Any]) -> float:
    tempo = scene.get("timeline", {}).get("tempo", [])
    return tempo[0]["bpm"] if tempo else 120.0


def op_inpaint(scene: Dict, req: EditRequest) -> Tuple[Dict, List[str]]:
    """Replace notes in the selected time range (12.1)."""
    new = copy.deepcopy(scene)
    bpm = _get_bpm(new)
    s0 = req.selection.start_s or 0.0
    s1 = req.selection.end_s or s0 + 4.0
    b0, b1 = s0 / (60.0 / bpm), s1 / (60.0 / bpm)
    rng = np.random.default_rng(req.seed)
    changed = []
    for part in new.get("parts", []):
        if req.selection.part_id and part.get("id") != req.selection.part_id:
            continue
        notes = part.get("notes", [])
        # Remove notes in range.
        kept = [n for n in notes
                if not (b0 <= n["start_beats"] < b1)]
        removed = len(notes) - len(kept)
        # Generate replacement notes from the instruction (simple: fill
        # with a scale run guided by keywords).
        new_notes = _generate_fill(b0, b1, req.instruction, rng)
        part["notes"] = sorted(kept + new_notes,
                               key=lambda n: n["start_beats"])
        if removed or new_notes:
            changed.append(f"part:{part.get('id')}")
    return new, changed


def _generate_fill(b0: float, b1: float, instruction: str,
                   rng: np.random.Generator) -> List[Dict]:
    notes = []
    # Parse instruction for hints: "sparse", "dense", "high", "low".
    dense = "dense" in instruction.lower()
    step = 0.5 if dense else 1.0
    scale = [60, 62, 64, 65, 67, 69, 71, 72]
    t = b0
    i = 0
    while t < b1:
        pitch = scale[i % len(scale)]
        if "high" in instruction.lower():
            pitch += 12
        if "low" in instruction.lower():
            pitch -= 12
        notes.append({"pitch": pitch, "start_beats": round(t, 3),
                      "duration_beats": step * 0.9,
                      "velocity": round(float(rng.uniform(0.6, 0.9)), 2)})
        t += step
        i += 1
    return notes


def op_continue(scene: Dict, req: EditRequest) -> Tuple[Dict, List[str]]:
    """Extend the track by new bars (12.1)."""
    new = copy.deepcopy(scene)
    bpm = _get_bpm(new)
    # Instruction like "add 4 bars" or default 4.
    import re
    m = re.search(r"(\d+)\s*bars?", req.instruction.lower())
    bars = int(m.group(1)) if m else 4
    beats = bars * 4
    # Find the end.
    end_beats = 0.0
    for part in new.get("parts", []):
        for n in part.get("notes", []):
            end_beats = max(end_beats,
                            n["start_beats"] + n["duration_beats"])
    # Extend each part by copying its last phrase transposed.
    rng = np.random.default_rng(req.seed)
    for part in new.get("parts", []):
        notes = part.get("notes", [])
        if not notes:
            continue
        # Copy the last `beats` worth, shifted.
        phrase = [n for n in notes if n["start_beats"] >= end_beats - beats]
        if not phrase:
            phrase = notes[-4:]
        shift = end_beats - min(n["start_beats"] for n in phrase)
        for n in phrase:
            nn = dict(n)
            nn["start_beats"] = round(n["start_beats"] + shift, 3)
            # Slight variation.
            nn["velocity"] = round(float(np.clip(
                n.get("velocity", 0.8) + rng.normal(0, 0.05), 0.1, 1.0)), 2)
            notes.append(nn)
        part["notes"] = sorted(notes, key=lambda n: n["start_beats"])
    # Extend sections.
    if new.get("sections"):
        last = new["sections"][-1]
        new_sec = copy.deepcopy(last)
        new_sec["bars"] = [last["bars"][1] + 1, last["bars"][1] + bars]
        new_sec["name"] = last.get("name", "section") + "-continued"
        new["sections"].append(new_sec)
    return new, ["timeline"] + [f"part:{p.get('id')}"
                                for p in new.get("parts", [])]


def op_regenerate_section(scene: Dict, req: EditRequest) -> Tuple[Dict, List[str]]:
    """Produce another verse/chorus without losing identity (12.1)."""
    new = copy.deepcopy(scene)
    target = (req.selection.element or "").replace("section:", "")
    rng = np.random.default_rng(req.seed)
    changed = []
    for sec in new.get("sections", []):
        if sec.get("id") != target and sec.get("name") != target:
            continue
        # Regenerate: vary the parts within this section's bar range.
        b0, b1 = sec["bars"][0] * 4, (sec["bars"][1] + 1) * 4
        for part in new.get("parts", []):
            notes = part.get("notes", [])
            in_sec = [n for n in notes if b0 <= n["start_beats"] < b1]
            for n in in_sec:
                # Rhythmic variation, same pitches (keeps identity).
                if rng.random() < 0.3:
                    n["start_beats"] = round(
                        n["start_beats"] + rng.choice([-0.5, 0.5]), 3)
                n["velocity"] = round(float(np.clip(
                    n.get("velocity", 0.8) + rng.normal(0, 0.08),
                    0.1, 1.0)), 2)
            changed.append(f"part:{part.get('id')}")
        changed.append(f"section:{sec.get('id', sec.get('name'))}")
    return new, changed


def op_part_stem(scene: Dict, req: EditRequest) -> Tuple[Dict, List[str]]:
    """Generate, replace, remove, or rebalance a part (12.1)."""
    new = copy.deepcopy(scene)
    instruction = req.instruction.lower()
    changed = []
    if "remove" in instruction and req.selection.part_id:
        pid = req.selection.part_id
        new["parts"] = [p for p in new.get("parts", [])
                        if p.get("id") != pid]
        changed.append(f"part:{pid}")
    elif "rebalance" in instruction or "quieter" in instruction or \
            "louder" in instruction:
        factor = 0.7 if "quieter" in instruction else 1.3
        for part in new.get("parts", []):
            if req.selection.part_id and \
                    part.get("id") != req.selection.part_id:
                continue
            for n in part.get("notes", []):
                n["velocity"] = round(float(np.clip(
                    n.get("velocity", 0.8) * factor, 0.05, 1.0)), 2)
            changed.append(f"part:{part.get('id')}")
    elif "generate" in instruction or "add" in instruction:
        # Generate a new part from the instruction.
        pid = f"part-{len(new.get('parts', [])) + 1}"
        bpm = _get_bpm(new)
        rng = np.random.default_rng(req.seed)
        notes = _generate_fill(0, 16, instruction, rng)
        new.setdefault("parts", []).append(
            {"id": pid, "role": "keys", "notes": notes})
        changed.append(f"part:{pid}")
    return new, changed


def op_arrangement(scene: Dict, req: EditRequest) -> Tuple[Dict, List[str]]:
    """Add/remove instrument, change density, shift section energy."""
    new = copy.deepcopy(scene)
    instruction = req.instruction.lower()
    changed = []
    if "density" in instruction:
        up = "increase" in instruction or "more" in instruction
        for part in new.get("parts", []):
            notes = part.get("notes", [])
            if up:
                # Double some notes.
                rng = np.random.default_rng(req.seed)
                extra = []
                for n in notes[::2]:
                    nn = dict(n)
                    nn["start_beats"] = round(n["start_beats"] + 0.5, 3)
                    extra.append(nn)
                part["notes"] = sorted(notes + extra,
                                       key=lambda n: n["start_beats"])
            else:
                part["notes"] = notes[::2]
            changed.append(f"part:{part.get('id')}")
    if "energy" in instruction:
        # Shift energy: scale velocities in the selected section.
        target = (req.selection.element or "").replace("section:", "")
        up = "up" in instruction or "raise" in instruction
        factor = 1.25 if up else 0.8
        for sec in new.get("sections", []):
            if sec.get("id") != target and sec.get("name") != target:
                continue
            b0, b1 = sec["bars"][0] * 4, (sec["bars"][1] + 1) * 4
            for part in new.get("parts", []):
                for n in part.get("notes", []):
                    if b0 <= n["start_beats"] < b1:
                        n["velocity"] = round(float(np.clip(
                            n.get("velocity", 0.8) * factor, 0.05, 1.0)), 2)
            changed.append(f"section:{sec.get('id', sec.get('name'))}")
    return new, changed


def op_lyric_edit(scene: Dict, req: EditRequest) -> Tuple[Dict, List[str]]:
    """Change a lyric line and mark it for realignment (12.1)."""
    new = copy.deepcopy(scene)
    # selection.element like "lyrics.line.3"; instruction is the new text.
    element = req.selection.element or ""
    idx = 0
    import re
    m = re.search(r"line\.(\d+)", element)
    if m:
        idx = int(m.group(1))
    lines = new.get("lyrics", {}).get("lines", [])
    if 0 <= idx < len(lines):
        lines[idx]["text"] = req.instruction
        lines[idx]["realignment_needed"] = True
    return new, [f"lyrics.line.{idx}"]


def op_performance_replace(scene: Dict, req: EditRequest) -> Tuple[Dict, List[str]]:
    """Re-perform a phrase with a different instruction (12.1)."""
    new = copy.deepcopy(scene)
    rng = np.random.default_rng(req.seed)
    instruction = req.instruction.lower()
    changed = []
    s0 = req.selection.start_s or 0.0
    s1 = req.selection.end_s or 4.0
    bpm = _get_bpm(new)
    b0, b1 = s0 / (60.0 / bpm), s1 / (60.0 / bpm)
    for part in new.get("parts", []):
        if req.selection.part_id and part.get("id") != req.selection.part_id:
            continue
        for n in part.get("notes", []):
            if b0 <= n["start_beats"] < b1:
                if "softer" in instruction or "gentle" in instruction:
                    n["velocity"] = round(n.get("velocity", 0.8) * 0.6, 2)
                elif "stronger" in instruction or "accent" in instruction:
                    n["velocity"] = round(
                        min(1.0, n.get("velocity", 0.8) * 1.4), 2)
                # Timing: push or lay back.
                if "push" in instruction:
                    n["start_beats"] = round(n["start_beats"] - 0.05, 3)
                elif "lay back" in instruction or "laid" in instruction:
                    n["start_beats"] = round(n["start_beats"] + 0.05, 3)
        changed.append(f"part:{part.get('id')}")
    return new, changed


def op_asset_swap(scene: Dict, req: EditRequest) -> Tuple[Dict, List[str]]:
    """Change the voice character, instrument, or preset (12.1)."""
    new = copy.deepcopy(scene)
    # instruction names the new asset: "voice:xyz v2" or "preset:abc".
    new_asset = req.instruction.strip()
    changed = []
    if new_asset.startswith("voice:"):
        for v in new.get("vocals", []):
            v["asset"] = new_asset
            changed.append(f"vocal:{v.get('id')}")
    elif new_asset.startswith("preset:"):
        new["production"]["preset"] = new_asset
        changed.append("production")
    elif new_asset.startswith("instrument:"):
        pid = req.selection.part_id
        for part in new.get("parts", []):
            if pid and part.get("id") != pid:
                continue
            part["instrument"] = new_asset
            changed.append(f"part:{part.get('id')}")
    # Record the asset in render metadata.
    new["render"]["asset_versions"][new_asset] = "swapped"
    return new, changed


def op_reference_condition(scene: Dict, req: EditRequest) -> Tuple[Dict, List[str]]:
    """Guide the edit with a supplied reference (12.1)."""
    # Reference provides: density, articulation hints, or a melody.
    new = copy.deepcopy(scene)
    ref = req.reference or {}
    changed = []
    if "density" in ref:
        # Apply the reference's density to the arrangement.
        sub = EditRequest(operation="arrangement",
                          scene_version_id=req.scene_version_id,
                          selection=req.selection,
                          instruction="density increase" if ref["density"] > 0.5
                          else "density decrease",
                          seed=req.seed)
        new, changed = op_arrangement(new, sub)
    if "melody" in ref:
        # Use the reference melody for the selected part.
        for part in new.get("parts", []):
            if req.selection.part_id and \
                    part.get("id") != req.selection.part_id:
                continue
            part["notes"] = ref["melody"]
            changed.append(f"part:{part.get('id')}")
    return new, changed


def op_automation_edit(scene: Dict, req: EditRequest) -> Tuple[Dict, List[str]]:
    """Change a parameter curve; re-render only what it touches (12.1)."""
    new = copy.deepcopy(scene)
    # instruction: "volume 0-4s to 0.9" or selection.element "automation.volume".
    element = req.selection.element or "automation.volume"
    param = element.replace("automation.", "")
    # Parse target value from instruction.
    import re
    m = re.search(r"to\s+([\d.]+)", req.instruction)
    value = float(m.group(1)) if m else 0.8
    s0 = req.selection.start_s or 0.0
    s1 = req.selection.end_s or 4.0
    auto = new.setdefault("automation", [])
    # Replace or add points in range.
    auto = [p for p in auto if not (p.get("param") == param and
                                    s0 <= p.get("time_s", 0) < s1)]
    auto.append({"param": param, "time_s": s0, "value": value})
    auto.append({"param": param, "time_s": s1, "value": value})
    new["automation"] = sorted(auto, key=lambda p: p["time_s"])
    return new, [f"automation:{param}"]


OPERATIONS = {
    "inpaint": op_inpaint,
    "continue": op_continue,
    "regenerate_section": op_regenerate_section,
    "part_stem": op_part_stem,
    "arrangement": op_arrangement,
    "lyric_edit": op_lyric_edit,
    "performance_replace": op_performance_replace,
    "asset_swap": op_asset_swap,
    "reference_condition": op_reference_condition,
    "automation_edit": op_automation_edit,
}
