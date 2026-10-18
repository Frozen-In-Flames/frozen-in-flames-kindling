"""Per-track record (Part 4.2).

Each record stores: content hash; source and acquisition method; license or
consent status and its terms; allowed uses (train, evaluate, none);
processing versions; every derived label with a confidence; split
assignment; and a deletion handle.
"""

from __future__ import annotations

from typing import Any, Dict, List

from jsonschema import validate as _js_validate

LABEL_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "value": {},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "method": {"type": "string"},
        "model_version": {"type": "string"},
    },
    "required": ["value", "confidence", "method"],
    "additionalProperties": True,
}

RECORD_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://frozen-in-flames.github.io/schemas/kindling-data-record-4.0.0.json",
    "title": "Kindling Data Record",
    "type": "object",
    "properties": {
        "kind": {"const": "kindling/data-record"},
        "schema_version": {"type": "string"},
        "record_id": {"type": "string"},
        "content_hash": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
        "fingerprint": {"type": "string"},
        "source": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "acquisition": {"type": "string"},
                "acquired_at": {"type": "string"},
            },
            "required": ["name", "acquisition"],
        },
        "license": {
            "type": "object",
            "properties": {
                "status": {"enum": ["cleared", "pending", "restricted", "unknown"]},
                "terms": {"type": "string"},
                "attribution": {"type": "string"},
                "territory": {"type": "string"},
                "training_allowed": {"type": "boolean"},
                "commercial_allowed": {"type": "boolean"},
            },
            "required": ["status", "training_allowed"],
        },
        "consent": {
            "type": "object",
            "properties": {
                "voice_consent_id": {"type": ["string", "null"]},
                "uploader_owns_rights": {"type": "boolean"},
            },
        },
        "allowed_uses": {
            "type": "array",
            "items": {"enum": ["train", "evaluate", "none"]},
        },
        "processing_versions": {"type": "object"},
        "labels": {"type": "object", "additionalProperties": LABEL_SCHEMA},
        "split": {"enum": ["train", "validate", "test", "unassigned"]},
        "deleted": {"type": "boolean"},
        "deletion": {
            "type": ["object", "null"],
            "properties": {
                "handle": {"type": "string"},
                "deleted_at": {"type": "string"},
                "reason": {"type": "string"},
                "cascaded_assets": {"type": "array", "items": {"type": "string"}},
            },
        },
        "derived_asset_ids": {"type": "array", "items": {"type": "string"}},
        "quality_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "flags": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "kind", "schema_version", "record_id", "content_hash", "source",
        "license", "allowed_uses", "processing_versions", "labels",
        "split", "deleted",
    ],
    "additionalProperties": True,
}


def make_record(record_id: str, content_hash: str, source: Dict[str, Any],
                license: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "kind": "kindling/data-record",
        "schema_version": "4.0.0",
        "record_id": record_id,
        "content_hash": content_hash,
        "fingerprint": "",
        "source": source,
        "license": license,
        "consent": {"voice_consent_id": None, "uploader_owns_rights": False},
        "allowed_uses": [],
        "processing_versions": {},
        "labels": {},
        "split": "unassigned",
        "deleted": False,
        "deletion": None,
        "derived_asset_ids": [],
        "quality_score": 0.0,
        "flags": [],
    }


def validate_record(record: Dict[str, Any]) -> None:
    _js_validate(instance=record, schema=RECORD_SCHEMA)


def label(value: Any, confidence: float, method: str,
          model_version: str = "") -> Dict[str, Any]:
    """One derived label with its confidence. Low confidence is marked, not
    hidden (Part 4.3): the value stays, and training code thresholds it."""
    entry: Dict[str, Any] = {"value": value, "confidence": confidence, "method": method}
    if model_version:
        entry["model_version"] = model_version
    return entry


def low_confidence_labels(record: Dict[str, Any], threshold: float = 0.5) -> List[str]:
    return [name for name, lab in record.get("labels", {}).items()
            if lab.get("confidence", 0.0) < threshold]
