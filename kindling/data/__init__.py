"""Data pipeline (Build Manual Part 4).

Reproducible, traceable data with labels good enough to train structured,
editable models. Every track gets a full record (4.2); splits never leak
(4.3); deletion propagates; low-confidence labels are marked, not hidden.
"""

from kindling.data.record import RECORD_SCHEMA, make_record, validate_record
from kindling.data.pipeline import Pipeline
from kindling.data.ledger import LicenseLedger, build_manifest

__all__ = [
    "RECORD_SCHEMA",
    "make_record",
    "validate_record",
    "Pipeline",
    "LicenseLedger",
    "build_manifest",
]
