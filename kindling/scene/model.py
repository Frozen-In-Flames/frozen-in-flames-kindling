"""Scene model helpers (Part 3.1, 3.2, 3.3).

Scenes are plain dicts validated against the JSON Schema in schema.py, so the
open documented format is the in-memory format. These helpers build scenes,
attach per-element metadata, and convert between bars and seconds.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from jsonschema import validate as _js_validate

from kindling.scene.schema import SCENE_SCHEMA

SOURCES = ("user", "planner", "inferred", "imported")
REALIZATION_LEVELS = ("intent", "symbolic", "performance", "audio")
SECTION_TYPES = ("intro", "verse", "pre-chorus", "chorus", "bridge", "outro", "custom")


def make_element_meta(
    source: str = "user",
    confidence: float = 1.0,
    locked: bool = False,
    realization: str = "intent",
) -> Dict[str, Any]:
    """Per-element metadata, Part 3.2."""
    if source not in SOURCES:
        raise ValueError(f"unknown source {source!r}")
    if realization not in REALIZATION_LEVELS:
        raise ValueError(f"unknown realization level {realization!r}")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be in [0, 1]")
    return {
        "source": source,
        "confidence": confidence,
        "locked": locked,
        "realization": realization,
    }


def make_scene(
    scene_id: Optional[str] = None,
    parent: Optional[str] = None,
    created_by: str = "user",
) -> Dict[str, Any]:
    """A new, empty scene. Partially realized scenes are valid: elements can
    be added at any realization level (Part 3.3)."""
    return {
        "kind": "kindling/scene",
        "schema_version": "3.0.0",
        "id": scene_id,
        "parent": parent,
        "timeline": {
            "tempo": [{"bar": 1, "bpm": 120.0}],
            "meter": [{"bar": 1, "sig": "4/4"}],
            "key": [{"bar": 1, "key": "C major"}],
        },
        "sections": [],
        "harmony": [],
        "melody": {"notes": [], "contour": None, "meta": make_element_meta()},
        "lyrics": {"lines": []},
        "parts": [],
        "vocals": [],
        "automation": [],
        "production": {
            "preset": None,
            "routing": {},
            "sends": [],
            "meta": make_element_meta(),
        },
        "render": {
            "sample_rate": 48000,
            "seed": 0,
            "tier": "draft",
            "model_versions": {},
            "asset_versions": {},
        },
        "provenance": {
            "created_by": created_by,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tool": "kindling",
        },
    }


def validate_scene(scene: Dict[str, Any]) -> None:
    """Raise jsonschema.ValidationError if the scene is not a valid scene."""
    _js_validate(instance=scene, schema=SCENE_SCHEMA)


def beats_per_bar(sig: str) -> float:
    num, den = sig.split("/")
    return float(num) * 4.0 / float(den)


def _map_lookup(entries: List[Dict[str, Any]], bar: int, key: str, default: Any) -> Any:
    value = default
    for entry in sorted(entries, key=lambda e: e["bar"]):
        if entry["bar"] <= bar:
            value = entry[key]
        else:
            break
    return value


def bar_to_seconds(scene: Dict[str, Any], bar: int) -> float:
    """Seconds at the start of the given 1-based bar, from the tempo map."""
    timeline = scene["timeline"]
    first_bar = min(e["bar"] for e in timeline["tempo"])
    seconds = 0.0
    for b in range(first_bar, bar):
        bpm = _map_lookup(timeline["tempo"], b, "bpm", 120.0)
        sig = _map_lookup(timeline["meter"], b, "sig", "4/4")
        seconds += beats_per_bar(sig) * 60.0 / bpm
    return seconds


def bar_duration_seconds(scene: Dict[str, Any], bar: int) -> float:
    bpm = _map_lookup(scene["timeline"]["tempo"], bar, "bpm", 120.0)
    sig = _map_lookup(scene["timeline"]["meter"], bar, "sig", "4/4")
    return beats_per_bar(sig) * 60.0 / bpm


def scene_to_seconds_map(scene: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    """Section id -> {start_s, end_s}, Part 3.1 (boundaries in bars and seconds)."""
    result = {}
    for section in scene.get("sections", []):
        first, last = section["bars"]
        start = bar_to_seconds(scene, first)
        end = bar_to_seconds(scene, last) + bar_duration_seconds(scene, last)
        result[section["id"]] = {"start_s": start, "end_s": end}
    return result


def clone_scene(scene: Dict[str, Any]) -> Dict[str, Any]:
    return copy.deepcopy(scene)
