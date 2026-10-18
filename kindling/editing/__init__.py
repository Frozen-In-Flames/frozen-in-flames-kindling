"""Editing engine (Part 12)."""

from .contract import EditReport, EditRequest, Selection
from .deps import DependencyGraph
from .locality import (crossfade_edits, edit_mask, outside_mask_distance,
                       seam_score, verify_locked)
from .operations import OPERATIONS
from .takes import TakeManager

__all__ = [
    "EditRequest", "EditReport", "Selection", "OPERATIONS",
    "DependencyGraph", "TakeManager",
    "edit_mask", "outside_mask_distance", "seam_score", "verify_locked",
    "crossfade_edits",
]
