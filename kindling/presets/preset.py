"""Preset format (10.2): an editable graph, not an opaque embedding.

A preset is a JSON-serializable dict covering: source/role choices,
arrangement and register tendencies, effects with order/parameters/
ranges, spatial/dynamic/tonal targets, per-section automation. Every
parameter has a range so the preset stays editable.
"""

from typing import Any, Dict, List

PRESET_SCHEMA_VERSION = "1.0"

EFFECT_SPECS = {
    "lowshelf": {"freq": (40, 500), "gain_db": (-12, 12)},
    "highshelf": {"freq": (4000, 16000), "gain_db": (-12, 12)},
    "compressor": {"threshold_db": (-40, 0), "ratio": (1.0, 10.0),
                   "attack_ms": (0.5, 50.0), "release_ms": (20.0, 500.0)},
    "delay": {"time_ms": (20, 500), "feedback": (0.0, 0.7),
              "mix": (0.0, 0.6)},
    "widener": {"width": (0.5, 2.0)},
}


def make_preset(name: str, chain: List[Dict[str, Any]],
                targets: Dict[str, Any] = None,
                roles: List[str] = None,
                sections: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build a validated preset dict."""
    for fx in chain:
        if fx["type"] not in EFFECT_SPECS:
            raise ValueError(f"unknown effect {fx['type']!r}")
        for param, (lo, hi) in EFFECT_SPECS[fx["type"]].items():
            val = fx.get("params", {}).get(param)
            if val is not None and not (lo <= val <= hi):
                raise ValueError(
                    f"{fx['type']}.{param}={val} outside [{lo}, {hi}]")
    return {
        "schema": PRESET_SCHEMA_VERSION,
        "name": name,
        "chain": chain,
        "targets": targets or {},
        "roles": roles or [],
        "sections": sections or [],
    }


def edit_preset(preset: Dict[str, Any], effect_index: int,
                param: str, value: float) -> Dict[str, Any]:
    """Return a new preset with one parameter changed (editability)."""
    import copy
    new = copy.deepcopy(preset)
    fx = new["chain"][effect_index]
    lo, hi = EFFECT_SPECS[fx["type"]][param]
    if not (lo <= value <= hi):
        raise ValueError(f"{param}={value} outside [{lo}, {hi}]")
    fx["params"][param] = value
    return new
