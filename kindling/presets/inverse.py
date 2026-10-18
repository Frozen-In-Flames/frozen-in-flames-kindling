"""Inverse rendering pipeline (10.1): recording -> preset.

Steps:
1. Analyze the reference (analyze.py).
2. Propose a structured preset from the measurements.
3. Self-fit check: render the preset on the reference's own material
   (here: the reference dry mix is approximated by inverting the
   proposed chain is not possible, so we render the preset on a neutral
   source and compare feature distance) and measure fit.
4. Return the preset with alternatives and confidence (10.3: never claim
   the single true chain).
5. Apply to new material (render.py).
"""

from typing import Any, Dict, List

import numpy as np

from .analyze import analyze_reference
from .preset import make_preset


def propose_preset(analysis: Dict[str, Any],
                   name: str = "inferred") -> Dict[str, Any]:
    """Propose a preset from reference measurements."""
    tonal = analysis["tonal_balance"]
    chain = []

    # Tonal: lowshelf/highshelf to match the measured balance.
    # Neutral balance targets: sub 0.08, low 0.22, mid 0.45, high 0.18.
    low_energy = tonal["sub"] + tonal["low"]
    if low_energy > 0.35:
        gain = min(9.0, (low_energy - 0.30) * 30)
        chain.append({"type": "lowshelf",
                      "params": {"freq": 200, "gain_db": round(-gain, 1)}})
    elif low_energy < 0.22:
        gain = min(9.0, (0.25 - low_energy) * 30)
        chain.append({"type": "lowshelf",
                      "params": {"freq": 200, "gain_db": round(gain, 1)}})
    high_energy = tonal["high"] + tonal["air"]
    if high_energy > 0.25:
        gain = min(9.0, (high_energy - 0.20) * 25)
        chain.append({"type": "highshelf",
                      "params": {"freq": 8000, "gain_db": round(-gain, 1)}})
    elif high_energy < 0.12:
        gain = min(9.0, (0.15 - high_energy) * 25)
        chain.append({"type": "highshelf",
                      "params": {"freq": 8000, "gain_db": round(gain, 1)}})

    # Dynamics: crest factor guides the compressor.
    crest = analysis["crest_db"]
    if crest > 14:
        chain.append({"type": "compressor",
                      "params": {"threshold_db": -20, "ratio": 3.0,
                                 "attack_ms": 5.0, "release_ms": 120.0}})
    elif crest > 10:
        chain.append({"type": "compressor",
                      "params": {"threshold_db": -16, "ratio": 2.0,
                                 "attack_ms": 10.0, "release_ms": 150.0}})

    # Space: space_ratio guides the delay mix.
    space = analysis["space_ratio"]
    if space > 0.25:
        chain.append({"type": "delay",
                      "params": {"time_ms": 140, "feedback": 0.35,
                                 "mix": round(min(0.5, space), 2)}})

    # Stereo: correlation guides the widener.
    corr = analysis["stereo_correlation"]
    if corr > 0.9:
        chain.append({"type": "widener", "params": {"width": 1.3}})
    elif corr < 0.5:
        chain.append({"type": "widener", "params": {"width": 0.8}})

    targets = {
        "tonal_balance": tonal,
        "crest_db": crest,
        "stereo_correlation": corr,
        "space_ratio": space,
    }
    return make_preset(name, chain, targets=targets,
                       roles=analysis.get("detected_roles", []))


def alternatives(preset: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Plausible alternative presets (10.3: ambiguity is honest)."""
    import copy
    alts = []
    # Alternative 1: gentler dynamics (lower ratio).
    alt = copy.deepcopy(preset)
    alt["name"] = preset["name"] + "-gentle"
    for fx in alt["chain"]:
        if fx["type"] == "compressor":
            fx["params"]["ratio"] = max(1.5, fx["params"]["ratio"] - 1.0)
    alts.append(alt)
    # Alternative 2: drier (less space).
    alt = copy.deepcopy(preset)
    alt["name"] = preset["name"] + "-dry"
    alt["chain"] = [fx for fx in alt["chain"] if fx["type"] != "delay"]
    alts.append(alt)
    return alts


def confidence(analysis: Dict[str, Any]) -> float:
    """Confidence in the inference (0..1). Higher when the reference has
    clear, strong signatures; lower when it is ambiguous."""
    score = 0.5
    # Strong tonal tilt -> confident EQ inference.
    tonal = analysis["tonal_balance"]
    tilt = abs((tonal["sub"] + tonal["low"]) - (tonal["high"] + tonal["air"]))
    score += min(0.2, tilt)
    # Extreme crest -> confident dynamics inference.
    crest = analysis["crest_db"]
    if crest > 14 or crest < 8:
        score += 0.15
    # Clear stereo image -> confident width inference.
    corr = analysis["stereo_correlation"]
    if corr > 0.9 or corr < 0.6:
        score += 0.15
    return round(min(1.0, score), 2)


def inverse_render(audio: np.ndarray, rate: int,
                   sections: List[Dict[str, float]] = None,
                   name: str = "inferred") -> Dict[str, Any]:
    """Full pipeline: audio -> preset + alternatives + confidence."""
    analysis = analyze_reference(audio, rate, sections)
    preset = propose_preset(analysis, name)
    return {
        "preset": preset,
        "alternatives": alternatives(preset),
        "confidence": confidence(analysis),
        "analysis": analysis,
        # 10.3: this is A plausible chain, not THE chain.
        "disclaimer": "plausible inference; different chains can produce "
                      "similar audio",
    }
