"""Prompt interpreter (Part 6.1).

Converts natural language, tags, lyrics, and controls into a draft scene.
MUST output a scene the user can read and MUST list its assumptions.
This reference implementation is deterministic and rule-driven: it extracts
tempo, key, sections, and mood from text, and records every default it chose
as an explicit assumption instead of hiding it.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from kindling.interfaces import PromptInterpreter as PromptInterpreterABC
from kindling.scene.model import make_element_meta, make_scene

_TEMPO_RE = re.compile(r"(\d{2,3})\s*bpm", re.IGNORECASE)
_KEY_RE = re.compile(r"\b([A-G][#b]?)\s*(major|minor|min\b|maj\b)", re.IGNORECASE)
_SECTION_WORDS = {
    "intro": "intro", "verse": "verse", "pre-chorus": "pre-chorus",
    "prechorus": "pre-chorus", "chorus": "chorus", "bridge": "bridge",
    "outro": "outro",
}
_ENERGY_UP = ("energetic", "anthemic", "big", "huge", "powerful", "driving", "intense")
_ENERGY_DOWN = ("soft", "intimate", "sparse", "gentle", "quiet", "minimal", "laid-back", "laidback")
_DARK_WORDS = ("dark", "moody", "brooding", "haunting")


def interpret(prompt: str, lyrics: Optional[str] = None,
             **controls: Any) -> Dict[str, Any]:
    """Interpret a prompt into a draft scene plus an assumptions list."""
    assumptions: List[str] = []
    scene = make_scene(created_by="prompt-interpreter")

    tempo = controls.get("tempo")
    if tempo is None:
        match = _TEMPO_RE.search(prompt or "")
        if match:
            tempo = int(match.group(1))
        else:
            tempo = 120
            assumptions.append("assumed 120 BPM (no tempo in prompt)")
    scene["timeline"]["tempo"] = [{"bar": 1, "bpm": float(tempo)}]

    key = controls.get("key")
    if key is None:
        match = _KEY_RE.search(prompt or "")
        if match:
            note = match.group(1)
            quality = match.group(2).lower()
            quality = "minor" if quality.startswith("min") else "major"
            key = f"{note[0].upper()}{note[1:]} {quality}"
        else:
            lowered = (prompt or "").lower()
            if any(w in lowered for w in _DARK_WORDS):
                key = "A minor"
                assumptions.append("assumed A minor (dark mood words, no key in prompt)")
            else:
                key = "C major"
                assumptions.append("assumed C major (no key in prompt)")
    scene["timeline"]["key"] = [{"bar": 1, "key": key}]

    meter = controls.get("meter", "4/4")
    if "meter" not in controls:
        assumptions.append("assumed 4/4 (no meter in prompt)")
    scene["timeline"]["meter"] = [{"bar": 1, "sig": meter}]

    lowered = (prompt or "").lower()
    found = [name for word, name in _SECTION_WORDS.items() if word in lowered]
    sections = controls.get("sections") or found or ["verse", "chorus"]
    if not controls.get("sections") and not found:
        assumptions.append("assumed verse/chorus form (no sections in prompt)")

    energy_bias = 0.0
    if any(w in lowered for w in _ENERGY_UP):
        energy_bias = 0.2
    if any(w in lowered for w in _ENERGY_DOWN):
        energy_bias = -0.2
    base_energy = controls.get("energy")
    if base_energy is None and energy_bias == 0.0:
        assumptions.append("assumed neutral energy (no mood words in prompt)")

    bar = 1
    for i, stype in enumerate(sections):
        length = 8 if stype in ("verse", "chorus") else 4
        default_energy = {"intro": 0.2, "verse": 0.35, "pre-chorus": 0.55,
                          "chorus": 0.8, "bridge": 0.6, "outro": 0.25}.get(stype, 0.5)
        energy = base_energy if base_energy is not None else min(1.0, max(0.0, default_energy + energy_bias))
        scene["sections"].append({
            "id": f"sec_{stype}{i + 1}",
            "type": stype,
            "bars": [bar, bar + length - 1],
            "energy": round(energy, 2),
            "density": round(min(1.0, energy + 0.1), 2),
            "meta": make_element_meta(source="inferred", confidence=0.6,
                                      realization="intent"),
        })
        bar += length

    if lyrics:
        lines = [ln.strip() for ln in lyrics.strip().splitlines() if ln.strip()]
        lyric_lines = []
        for i, text in enumerate(lines):
            lid = f"ln_{i + 1:02d}"
            lyric_lines.append({
                "id": lid, "text": text, "language": controls.get("language", "en"),
                "syllables": [], "meta": make_element_meta(source="user", confidence=1.0,
                                                          realization="symbolic"),
            })
        scene["lyrics"] = {"lines": lyric_lines}
        if scene["sections"]:
            per = max(1, len(lines) // len(scene["sections"]))
            for s_i, section in enumerate(scene["sections"]):
                section["lyrics"] = [f"ln_{j + 1:02d}"
                                     for j in range(s_i * per, min(len(lines), (s_i + 1) * per))]

    if prompt:
        scene["provenance"]["prompt"] = prompt
    return {"scene": scene, "assumptions": assumptions}


class ReferenceInterpreter(PromptInterpreterABC):
    @property
    def component_name(self) -> str:
        return "Prompt interpreter"

    @property
    def supported_tiers(self) -> List[str]:
        return ["draft", "studio", "hosted"]

    def interpret(self, prompt: str, **controls: Any) -> Dict[str, Any]:
        return interpret(prompt, **controls)
