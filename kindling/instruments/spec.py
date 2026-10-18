"""Virtual instruments: assets that perform parts musically (Part 9).

An instrument is not just a sound. It takes a part (notes) plus context
(harmony, tempo, density, neighboring parts) and produces a realistic
performance: articulation choices, timing, dynamics, phrasing. The same
instrument renders consistently across the whole song.

This module holds the asset specification (9.1). Performance behavior is
in performance.py, reference synthesizers in synth.py, and the
distillation workflow (9.3) in distill.py.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# 9.1: every instrument asset MUST expose these fields.
REQUIRED_SPEC_FIELDS = (
    "name",
    "pitch_range_midi",      # [low, high]
    "articulations",         # list of articulation names
    "dynamics",              # {"min_db", "max_db", "curve"}
    "timing",                # {"humanization_ms", "swing", ...}
    "phrasing",              # {"legato_overlap", "expression_curves"}
    "sound_design",          # {"tone", "attack", "space", ...} with ranges
    "context_inputs",        # ["harmony", "tempo", "density", "neighbors"]
    "version",
    "provenance",
)


@dataclass
class InstrumentAsset:
    """The instrument asset (9.1)."""
    name: str
    pitch_range_midi: List[int]
    articulations: List[str]
    dynamics: Dict[str, Any]
    timing: Dict[str, Any]
    phrasing: Dict[str, Any]
    sound_design: Dict[str, Any]
    context_inputs: List[str] = field(default_factory=lambda: [
        "harmony", "tempo", "density", "neighbors"])
    version: str = "v1"
    provenance: Dict[str, Any] = field(default_factory=dict)
    distillation_audit: Optional[Dict[str, Any]] = None

    def validate(self) -> List[str]:
        """Return a list of spec violations (empty means valid)."""
        problems = []
        lo, hi = self.pitch_range_midi
        if not (0 <= lo < hi <= 127):
            problems.append(f"pitch_range_midi invalid: {self.pitch_range_midi}")
        if not self.articulations:
            problems.append("articulations must be non-empty")
        for key in ("min_db", "max_db"):
            if key not in self.dynamics:
                problems.append(f"dynamics missing {key}")
        for param, spec in self.sound_design.items():
            if not isinstance(spec, dict) or "min" not in spec \
                    or "max" not in spec or "default" not in spec:
                problems.append(f"sound_design param {param!r} needs "
                                "min/max/default")
            elif not (spec["min"] <= spec["default"] <= spec["max"]):
                problems.append(f"sound_design param {param!r} default "
                                "outside range")
        return problems

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "pitch_range_midi": self.pitch_range_midi,
            "articulations": self.articulations,
            "dynamics": self.dynamics,
            "timing": self.timing,
            "phrasing": self.phrasing,
            "sound_design": self.sound_design,
            "context_inputs": self.context_inputs,
            "version": self.version,
            "provenance": self.provenance,
            "distillation_audit": self.distillation_audit,
        }


def make_guitar_asset() -> InstrumentAsset:
    """Reference guitar asset: strummed vs fingerpicked (9.2)."""
    return InstrumentAsset(
        name="kindling-guitar",
        pitch_range_midi=[40, 88],
        articulations=["strummed", "fingerpicked", "muted", "harmonic"],
        dynamics={"min_db": -24, "max_db": 0, "curve": "velocity"},
        timing={"humanization_ms": 8, "swing": 0.0, "strum_spread_ms": 12},
        phrasing={"legato_overlap": 0.1, "expression_curves": ["crescendo"]},
        sound_design={
            "tone": {"min": 0.0, "max": 1.0, "default": 0.5},
            "attack": {"min": 0.0, "max": 1.0, "default": 0.4},
            "space": {"min": 0.0, "max": 1.0, "default": 0.2},
        },
        provenance={"method": "reference", "teacher": "karplus-strong-hd"},
    )


def make_bass_asset() -> InstrumentAsset:
    """Reference bass asset: locks with the kick (9.2)."""
    return InstrumentAsset(
        name="kindling-bass",
        pitch_range_midi=[28, 55],
        articulations=["fingered", "picked", "slap", "muted"],
        dynamics={"min_db": -18, "max_db": 0, "curve": "velocity"},
        timing={"humanization_ms": 5, "swing": 0.0, "kick_lock": True},
        phrasing={"legato_overlap": 0.05, "expression_curves": []},
        sound_design={
            "tone": {"min": 0.0, "max": 1.0, "default": 0.6},
            "attack": {"min": 0.0, "max": 1.0, "default": 0.7},
            "space": {"min": 0.0, "max": 1.0, "default": 0.1},
        },
        provenance={"method": "reference", "teacher": "filtered-saw-hd"},
    )


def make_keys_asset() -> InstrumentAsset:
    """Reference electric-piano asset."""
    return InstrumentAsset(
        name="kindling-keys",
        pitch_range_midi=[36, 96],
        articulations=["sustained", "staccato", "tremolo"],
        dynamics={"min_db": -24, "max_db": 0, "curve": "velocity"},
        timing={"humanization_ms": 6, "swing": 0.0},
        phrasing={"legato_overlap": 0.2, "expression_curves": ["swell"]},
        sound_design={
            "tone": {"min": 0.0, "max": 1.0, "default": 0.5},
            "attack": {"min": 0.0, "max": 1.0, "default": 0.3},
            "space": {"min": 0.0, "max": 1.0, "default": 0.3},
        },
        provenance={"method": "reference", "teacher": "fm-ep-hd"},
    )
