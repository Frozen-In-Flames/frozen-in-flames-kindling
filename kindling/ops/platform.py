"""Staged results (18.2), tiers (18.3), monitoring (18.6), security (18.7)."""

import time
from typing import Any, Dict, List

import numpy as np


# 18.2: stream sketch -> draft -> final.
STAGES = ["sketch", "draft", "final"]


def staged_render(render_fn, params: Dict[str, Any]):
    """Yield (stage, audio) so users can decide before the full render."""
    for stage in STAGES:
        audio = render_fn(stage, params)
        yield stage, audio


# 18.3: local and hosted tiers. Bundles move without conversion.
TIERS = {
    "draft": {"location": "local", "max_seconds": 30},
    "studio": {"location": "local", "max_seconds": 300},
    "hosted": {"location": "hosted", "max_seconds": 3600},
}


def tier_for(project_seconds: float, requested: str = "draft") -> str:
    if requested not in TIERS:
        raise ValueError(f"unknown tier {requested!r}")
    # Upgrade if the project exceeds the tier's cap.
    for tier in ("draft", "studio", "hosted"):
        if project_seconds <= TIERS[tier]["max_seconds"]:
            # Never downgrade below requested.
            order = ["draft", "studio", "hosted"]
            return tier if order.index(tier) >= order.index(requested) \
                else requested
    return "hosted"


# 18.6: monitoring.
class Monitor:
    def __init__(self):
        self.latencies: Dict[str, List[float]] = {}
        self.crashes = 0
        self.cost_total = 0.0
        self.quality_regressions = 0

    def record_latency(self, stage: str, seconds: float):
        self.latencies.setdefault(stage, []).append(seconds)

    def record_crash(self):
        self.crashes += 1

    def record_cost(self, amount: float):
        self.cost_total += amount

    def record_regression(self):
        self.quality_regressions += 1

    def summary(self) -> Dict[str, Any]:
        import statistics
        return {
            "latency_p50_by_stage": {
                s: round(statistics.median(v), 3)
                for s, v in self.latencies.items() if v},
            "crashes": self.crashes,
            "cost_total": round(self.cost_total, 4),
            "quality_regressions": self.quality_regressions,
        }


# 18.7: security. Per-user access control, audit logging, rate limiting.
class AccessControl:
    def __init__(self):
        self.grants: Dict[str, Dict[str, List[str]]] = {}
        self.audit_log: List[Dict[str, Any]] = []
        self.rate_counts: Dict[str, List[float]] = {}

    def grant(self, user_id: str, resource: str, actions: List[str]):
        self.grants.setdefault(user_id, {}).setdefault(
            resource, []).extend(actions)

    def check(self, user_id: str, resource: str, action: str) -> bool:
        allowed = action in self.grants.get(user_id, {}).get(resource, [])
        # Log access to sensitive assets (voice characters).
        if resource.startswith("voice:") or not allowed:
            self.audit_log.append({"user": user_id, "resource": resource,
                                   "action": action, "allowed": allowed,
                                   "at": time.time()})
        return allowed

    def rate_limit(self, user_id: str, max_per_minute: int = 60) -> bool:
        now = time.time()
        calls = [t for t in self.rate_counts.get(user_id, [])
                 if now - t < 60]
        if len(calls) >= max_per_minute:
            return False
        calls.append(now)
        self.rate_counts[user_id] = calls
        return True
