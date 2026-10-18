"""Expressive vocal controls (Part 7).

Every control the manual requires, with valid ranges. validate_performance
rejects out-of-range values instead of clipping them silently: a performance
instruction the system cannot honor must fail loudly, not degrade quietly.
"""

from __future__ import annotations

from typing import Any, Dict

CONTROL_RANGES: Dict[str, Dict[str, Any]] = {
    "dynamics": {"min": 0.0, "max": 1.0, "default": 0.7,
                 "help": "overall loudness intention, 0 whisper-quiet to 1 full voice"},
    "breathiness": {"min": 0.0, "max": 1.0, "default": 0.15,
                    "help": "noise mixed with the pitched tone"},
    "vibrato_rate_hz": {"min": 0.0, "max": 9.0, "default": 5.5,
                        "help": "0 disables vibrato"},
    "vibrato_depth_cents": {"min": 0.0, "max": 120.0, "default": 35.0,
                            "help": "pitch excursion of the vibrato"},
    "belt": {"min": 0.0, "max": 1.0, "default": 0.0,
             "help": "brighter, more pressed harmonic balance"},
    "whisper": {"min": 0.0, "max": 1.0, "default": 0.0,
                "help": "1 is fully unvoiced; blends against pitched tone"},
    "phrasing_legato": {"min": 0.0, "max": 1.0, "default": 0.7,
                        "help": "connectedness between syllables"},
    "timing_push_ms": {"min": -120.0, "max": 120.0, "default": 0.0,
                       "help": "negative lays back, positive pushes ahead of the beat"},
    "doubles": {"min": 0, "max": 4, "default": 0,
                "help": "detuned unison copies; integer"},
    "harmonies": {"min": 0, "max": 4, "default": 0,
                  "help": "diatonic third-above copies; integer"},
}


def default_performance() -> Dict[str, Any]:
    return {name: spec["default"] for name, spec in CONTROL_RANGES.items()}


def validate_performance(performance: Dict[str, Any]) -> Dict[str, Any]:
    """Fill defaults and reject unknown or out-of-range controls."""
    result = default_performance()
    for name, value in performance.items():
        if name not in CONTROL_RANGES:
            raise ValueError(f"unknown expressive control {name!r}. "
                             f"Known: {sorted(CONTROL_RANGES)}")
        spec = CONTROL_RANGES[name]
        if spec["min"] == 0 and spec["max"] in (4,) and isinstance(spec["default"], int):
            if not isinstance(value, int) or not spec["min"] <= value <= spec["max"]:
                raise ValueError(f"{name} must be an int in "
                                 f"[{spec['min']}, {spec['max']}], got {value!r}")
        elif not spec["min"] <= value <= spec["max"]:
            raise ValueError(f"{name} must be in [{spec['min']}, {spec['max']}], "
                             f"got {value!r}")
        result[name] = value
    return result


def describe_controls() -> Dict[str, Dict[str, Any]]:
    return {k: dict(v) for k, v in CONTROL_RANGES.items()}
