"""Edit contract (12.2): every edit takes a scene version, a target
selection, an instruction, and a lock set. It returns a new scene
version, new audio for the affected elements, and an edit report.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Selection:
    """Target selection: time range, part, or element (12.2)."""
    start_s: Optional[float] = None
    end_s: Optional[float] = None
    part_id: Optional[str] = None
    element: Optional[str] = None  # e.g. "lyrics.line.3"

    def to_dict(self) -> Dict[str, Any]:
        return {"start_s": self.start_s, "end_s": self.end_s,
                "part_id": self.part_id, "element": self.element}


@dataclass
class EditRequest:
    operation: str
    scene_version_id: str
    selection: Selection
    instruction: str
    lock_set: List[str] = field(default_factory=list)
    seed: int = 0
    reference: Optional[Dict[str, Any]] = None  # reference conditioning


@dataclass
class EditReport:
    operation: str
    new_version_id: str
    changed: List[str]
    kept: List[str]
    seeds_used: Dict[str, int]
    assets_used: List[str]
    locked_verified: Dict[str, str]  # element -> "bit-exact"|"perceptual"
    locality: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {"operation": self.operation,
                "new_version_id": self.new_version_id,
                "changed": self.changed, "kept": self.kept,
                "seeds_used": self.seeds_used,
                "assets_used": self.assets_used,
                "locked_verified": self.locked_verified,
                "locality": self.locality}
