"""JSON Schema for the Kindling scene format (Part 3.1, 3.2, 3.3).

This is the open, documented scene format. The committed copy lives at
kindling/scene/scene.schema.json and is generated from SCENE_SCHEMA below;
the test suite asserts they match.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

ELEMENT_META_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "source": {"enum": ["user", "planner", "inferred", "imported"]},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "locked": {"type": "boolean"},
        "realization": {"enum": ["intent", "symbolic", "performance", "audio"]},
    },
    "required": ["source", "confidence", "locked", "realization"],
    "additionalProperties": False,
}

NOTE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "pitch": {"type": "integer", "minimum": 0, "maximum": 127},
        "start_beats": {"type": "number", "minimum": 0.0},
        "duration_beats": {"type": "number", "exclusiveMinimum": 0.0},
        "velocity": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": ["pitch", "start_beats", "duration_beats"],
    "additionalProperties": True,
}

ASSET_REF_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "version": {"type": "string"},
        "sha256": {"type": "string"},
    },
    "required": ["id", "version"],
    "additionalProperties": True,
}

SECTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "type": {"enum": ["intro", "verse", "pre-chorus", "chorus", "bridge", "outro", "custom"]},
        "bars": {"type": "array", "items": {"type": "integer", "minimum": 1}, "minItems": 2, "maxItems": 2},
        "energy": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "density": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "description": {"type": "string"},
        "lyrics": {"type": "array", "items": {"type": "string"}},
        "meta": ELEMENT_META_SCHEMA,
    },
    "required": ["id", "type", "bars", "meta"],
    "additionalProperties": True,
}

PART_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "role": {"type": "string"},
        "instrument": ASSET_REF_SCHEMA,
        "notes": {"type": "array", "items": NOTE_SCHEMA},
        "articulations": {"type": "array"},
        "dynamics": {"type": "array"},
        "expression": {"type": "object"},
        "meta": ELEMENT_META_SCHEMA,
    },
    "required": ["id", "role", "meta"],
    "additionalProperties": True,
}

VOCAL_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "voice": ASSET_REF_SCHEMA,
        "performance": {"type": "object"},
        "lines": {"type": "array", "items": {"type": "string"}},
        "meta": ELEMENT_META_SCHEMA,
    },
    "required": ["id", "meta"],
    "additionalProperties": True,
}

SCENE_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://frozen-in-flames.github.io/schemas/kindling-scene-3.0.0.json",
    "title": "Kindling Musical Scene",
    "description": "Build Manual Part 3: one shared representation connecting intent, symbolic music, performance, and audio.",
    "type": "object",
    "properties": {
        "kind": {"const": "kindling/scene"},
        "schema_version": {"type": "string"},
        "id": {"type": ["string", "null"]},
        "parent": {"type": ["string", "null"]},
        "timeline": {
            "type": "object",
            "properties": {
                "tempo": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"bar": {"type": "integer", "minimum": 1}, "bpm": {"type": "number", "exclusiveMinimum": 0}},
                        "required": ["bar", "bpm"],
                    },
                },
                "meter": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"bar": {"type": "integer", "minimum": 1}, "sig": {"type": "string", "pattern": "^[0-9]+/[0-9]+$"}},
                        "required": ["bar", "sig"],
                    },
                },
                "key": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"bar": {"type": "integer", "minimum": 1}, "key": {"type": "string"}},
                        "required": ["bar", "key"],
                    },
                },
            },
            "required": ["tempo", "meter", "key"],
        },
        "sections": {"type": "array", "items": SECTION_SCHEMA},
        "harmony": {"type": "array"},
        "melody": {"type": "object"},
        "lyrics": {"type": "object"},
        "parts": {"type": "array", "items": PART_SCHEMA},
        "vocals": {"type": "array", "items": VOCAL_SCHEMA},
        "automation": {"type": "array"},
        "production": {"type": "object"},
        "render": {
            "type": "object",
            "properties": {
                "sample_rate": {"type": "integer", "enum": [44100, 48000]},
                "seed": {"type": "integer"},
                "tier": {"enum": ["draft", "studio", "hosted"]},
                "model_versions": {"type": "object"},
                "asset_versions": {"type": "object"},
            },
            "required": ["sample_rate", "seed", "tier"],
        },
        "provenance": {"type": "object"},
    },
    "required": [
        "kind", "schema_version", "timeline", "sections", "parts",
        "vocals", "render", "provenance",
    ],
    "additionalProperties": True,
}

SCHEMA_FILE = os.path.join(os.path.dirname(__file__), "scene.schema.json")


def write_schema_file(path: str = SCHEMA_FILE) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(SCENE_SCHEMA, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


def load_schema_file(path: str = SCHEMA_FILE) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
