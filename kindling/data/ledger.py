"""License ledger, provenance queries, manifests, deletion (Part 4.2, 4.3).

Provenance is queryable: which training items came from a source, filtered
by license status. Deletion propagates: removing an item excludes it from
future training runs and lists the derived assets the policy must cascade
to (Part 4.3).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from kindling.data.record import validate_record


class LicenseLedger:
    def __init__(self, pipeline) -> None:
        self._pipeline = pipeline

    def records(self) -> List[Dict[str, Any]]:
        return self._pipeline.all_records()

    def get(self, record_id: str) -> Dict[str, Any]:
        return self._pipeline.record(record_id)

    def by_source(self, source_name: str) -> List[Dict[str, Any]]:
        """Answer: which training items came from this source (Part 4.3)."""
        return [r for r in self.records()
                if r["source"]["name"] == source_name and not r.get("deleted")]

    def by_license_status(self, status: str) -> List[Dict[str, Any]]:
        return [r for r in self.records()
                if r["license"]["status"] == status and not r.get("deleted")]

    def by_allowed_use(self, use: str) -> List[Dict[str, Any]]:
        return [r for r in self.records()
                if use in r.get("allowed_uses", []) and not r.get("deleted")]

    def by_split(self, split: str) -> List[Dict[str, Any]]:
        return [r for r in self.records()
                if r["split"] == split and not r.get("deleted")]

    def license_summary(self) -> Dict[str, int]:
        summary: Dict[str, int] = {}
        for record in self.records():
            if record.get("deleted"):
                continue
            status = record["license"]["status"]
            summary[status] = summary.get(status, 0) + 1
        return summary


def delete_record(pipeline, record_id: str, reason: str = "") -> Dict[str, Any]:
    """Delete a record. The deletion propagates: the record is excluded from
    every future manifest, and the derived assets that must be removed where
    policy requires are listed on the deletion handle (Part 4.3)."""
    record = pipeline.record(record_id)
    if record.get("deleted"):
        return record["deletion"]
    handle = {
        "handle": f"del_{record_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}",
        "deleted_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "cascaded_assets": list(record.get("derived_asset_ids", [])),
    }
    record["deleted"] = True
    record["deletion"] = handle
    record["allowed_uses"] = []
    validate_record(record)
    pipeline._persist(record)
    return handle


def build_manifest(pipeline, use: str) -> Dict[str, Any]:
    """A training/evaluation manifest: record ids that may be used for `use`.

    Deleted records are always excluded. Records whose license does not
    allow the use are excluded. The manifest pins the pipeline and record
    schema versions so the run is reproducible.
    """
    if use not in ("train", "evaluate"):
        raise ValueError(f"unknown manifest use: {use}")
    from kindling.data.pipeline import PROCESSING_VERSIONS
    ids = [r["record_id"] for r in pipeline.all_records()
           if not r.get("deleted") and use in r.get("allowed_uses", [])]
    return {
        "kind": "kindling/data-manifest",
        "use": use,
        "record_ids": sorted(ids),
        "count": len(ids),
        "processing_versions": dict(PROCESSING_VERSIONS),
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
