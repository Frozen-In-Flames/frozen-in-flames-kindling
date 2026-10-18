"""Structured renderer bake-off (Part 6.3).

Run the bake-off between autoregressive token models, parallel
latent-generation models, and a planner-plus-renderer hybrid. Judge them
against the Part 1 targets, not demos. The renderer stays behind the stable
interface (scene fragment in; audio and metadata out) so the winner can be
replaced later.

With no learned models registered yet, the reference deterministic renderer
runs as the baseline every bake-off must beat. Candidates register with an
approach label; the harness scores determinism, validity, coherence, and
cost, and ranks them.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

import numpy as np

from kindling.planning.coherence import coherence_report
from kindling.planning.renderer import ReferenceRenderer

APPROACHES = ("autoregressive", "parallel-latent", "planner-hybrid",
              "reference-deterministic")


def _valid_audio(audio: np.ndarray) -> bool:
    arr = np.asarray(audio, dtype=float)
    if arr.size == 0:
        return False
    if not np.all(np.isfinite(arr)):
        return False
    return float(np.max(np.abs(arr))) <= 1.0


def bake_off(candidates: List[Dict[str, Any]], suite: List[Dict[str, Any]],
             seed: int = 0) -> Dict[str, Any]:
    """candidates: [{name, approach, renderer}]. suite: list of scenes.
    Returns a ranked report."""
    results = []
    for candidate in candidates:
        name = candidate["name"]
        approach = candidate["approach"]
        if approach not in APPROACHES:
            raise ValueError(f"unknown approach {approach!r}")
        renderer = candidate["renderer"]
        times: List[float] = []
        coherence_passes = 0
        deterministic = True
        valid = True
        for scene in suite:
            started = time.perf_counter()
            first = renderer.render_fragment(scene, {}, seed, "draft")
            times.append(time.perf_counter() - started)
            second = renderer.render_fragment(scene, {}, seed, "draft")
            a1 = np.asarray(first["audio"]["samples"], dtype=float)
            a2 = np.asarray(second["audio"]["samples"], dtype=float)
            if a1.shape != a2.shape or not np.array_equal(a1, a2):
                deterministic = False
            if not _valid_audio(a1):
                valid = False
            rate = first["audio"]["sample_rate"]
            if coherence_report(scene, a1, rate)["passed"]:
                coherence_passes += 1
        score = (1.0 if valid else 0.0) * 0.25 + (1.0 if deterministic else 0.0) * 0.25
        score += (coherence_passes / max(1, len(suite))) * 0.5
        results.append({
            "name": name, "approach": approach,
            "mean_render_s": round(sum(times) / max(1, len(times)), 4),
            "valid": valid, "deterministic": deterministic,
            "coherence_pass_rate": round(coherence_passes / max(1, len(suite)), 3),
            "score": round(score, 3),
        })
    ranked = sorted(results, key=lambda r: r["score"], reverse=True)
    return {"candidates": ranked, "winner": ranked[0]["name"] if ranked else None,
            "suite_size": len(suite), "seed": seed}


def baseline_bake_off(suite: List[Dict[str, Any]], seed: int = 0) -> Dict[str, Any]:
    """The bake-off every learned renderer must beat: the reference."""
    return bake_off([{"name": "reference-deterministic",
                      "approach": "reference-deterministic",
                      "renderer": ReferenceRenderer()}],
                    suite, seed)
