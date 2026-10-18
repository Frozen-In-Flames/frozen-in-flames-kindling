"""Reliability (17.5), human protocol (17.2), reporting (17.6), gates (17.7)."""

import time
from typing import Any, Callable, Dict, List

import numpy as np


def reliability_report(render_fn: Callable[[int], np.ndarray],
                       check_fn: Callable[[np.ndarray], bool],
                       seeds: List[int],
                       severe_fn: Callable[[np.ndarray], bool] = None) -> Dict:
    """Render every suite prompt across seeds; report pass share and
    severe-failure rate (17.5)."""
    passes, severe = 0, 0
    for seed in seeds:
        audio = render_fn(seed)
        if check_fn(audio):
            passes += 1
        elif severe_fn and severe_fn(audio):
            severe += 1
    n = len(seeds)
    return {"seeds": n, "pass_rate": round(passes / n, 3),
            "severe_failure_rate": round(severe / n, 3),
            "passes": passes, "severe": severe}


# 17.2: human evaluation protocol (published, versioned).
HUMAN_PROTOCOL = {
    "version": "1.0.0",
    "blinding": "raters hear A/B without knowing the source",
    "raters": ["musicians", "producers", "vocalists", "listeners"],
    "dimensions": ["prompt_adherence", "composition", "vocal_quality",
                   "coherence", "production", "edit_success"],
    "scale": "1-5 per dimension",
}


def inter_rater_agreement(ratings: List[List[float]]) -> float:
    """Fleiss-like agreement: mean pairwise correlation across raters."""
    import numpy as np
    arr = np.array(ratings, dtype=float)
    if arr.shape[0] < 2:
        return 1.0
    corrs = []
    for i in range(arr.shape[0]):
        for j in range(i + 1, arr.shape[0]):
            c = np.corrcoef(arr[i], arr[j])[0, 1]
            if not np.isnan(c):
                corrs.append(float(c))
    return round(float(np.mean(corrs)) if corrs else 0.0, 3)


# 17.6: model cards and datasheets.
def model_card(name: str, version: str, details: Dict[str, Any]) -> Dict:
    return {"kind": "model-card", "name": name, "version": version,
            "intended_use": details.get("intended_use", ""),
            "limitations": details.get("limitations", ""),
            "evaluation": details.get("evaluation", {}),
            "created_at": time.strftime("%Y-%m-%d")}


def datasheet(name: str, version: str, details: Dict[str, Any]) -> Dict:
    return {"kind": "datasheet", "name": name, "version": version,
            "collection": details.get("collection", ""),
            "composition": details.get("composition", ""),
            "consent": details.get("consent", ""),
            "created_at": time.strftime("%Y-%m-%d")}


# 17.7: release gates.
def check_release_gates(results: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate the 8 release gates. results maps gate -> {"passed"}."""
    gates = ["quality", "vocals", "editing", "assets", "reliability",
             "reproducibility", "safety", "documentation"]
    outcome = {}
    for gate in gates:
        outcome[gate] = bool(results.get(gate, {}).get("passed", False))
    return {"gates": outcome,
            "release": all(outcome.values()),
            "blocked_by": [g for g, p in outcome.items() if not p]}
