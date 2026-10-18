"""Risk monitors (Part 21): code hooks for the early signals.

Each returns {"risk", "signal", "threshold", "tripped"}. Wire these into
the release gate review and the ops Monitor.
"""

from typing import Any, Dict, List

import numpy as np


def _report(risk: str, signal: float, threshold: float,
            higher_is_worse: bool = True) -> Dict[str, Any]:
    tripped = signal > threshold if higher_is_worse else signal < threshold
    return {"risk": risk, "signal": round(signal, 3),
            "threshold": threshold, "tripped": bool(tripped)}


def monitor_vocal_risk(wer: float, identity_sims: List[float]) -> Dict:
    """High WER or identity drift across sections (Part 21)."""
    drift = 1.0 - float(np.mean(identity_sims)) if identity_sims else 0.0
    return _report("vocals_unintelligible_or_unstable",
                   max(wer, drift), 0.25)


def monitor_edit_risk(outside_mask_db: float) -> Dict:
    """Large outside-mask difference (Part 21)."""
    return _report("edits_change_too_much", outside_mask_db, 3.0)


def monitor_coherence_risk(scores_by_length: Dict[str, float]) -> Dict:
    """Rater scores falling as length grows (Part 21)."""
    order = {"short": 0, "medium": 1, "long": 2}
    lengths = sorted(scores_by_length.keys(), key=lambda k: order.get(k, 99))
    if len(lengths) < 2:
        return _report("long_form_incoherence", 0.0, 0.5,
                       higher_is_worse=False)
    first = scores_by_length[lengths[0]]
    last = scores_by_length[lengths[-1]]
    drop = first - last
    return {"risk": "long_form_incoherence",
            "signal": round(drop, 3), "threshold": 0.5,
            "tripped": drop > 0.5}


def monitor_data_risk(ledger_gaps: int) -> Dict:
    """Gaps in the license ledger (Part 21)."""
    return _report("data_rights_uncertainty", float(ledger_gaps), 0.0)


def monitor_profile_risk(output_diversity: float) -> Dict:
    """Outputs converging on an average (Part 21). Lower diversity is worse."""
    return _report("profile_collapses_to_generic", output_diversity, 0.3,
                   higher_is_worse=False)


def monitor_preset_risk(transfer_pass_rate: float) -> Dict:
    """Preset transfer tests failing (Part 21)."""
    return _report("preset_inference_overclaims", transfer_pass_rate, 0.8,
                   higher_is_worse=False)


def monitor_reproducibility_risk(failures: int, total: int) -> Dict:
    """Old projects no longer re-render (Part 21)."""
    rate = failures / total if total else 0.0
    return _report("reproducibility_drift", rate, 0.05)


def monitor_demo_bias(suite_pass_rate: float,
                      demo_pass_rate: float) -> Dict:
    """Strong demos but weak suite results (Part 21)."""
    gap = demo_pass_rate - suite_pass_rate
    return _report("demo_bias", gap, 0.2)
