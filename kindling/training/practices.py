"""Ablations, checkpoints, and test-set guards (Part 16 practices).

- Run small-scale ablations before every large run. Record the decision
  each ablation informed.
- Evaluate checkpoints on the regression suite automatically; block
  promotion on regression.
- Store configs, data manifests, seeds, and code revisions with every
  checkpoint.
- Never tune on the test sets (enforced by TestSetGuard).
"""

import hashlib
import json
import os
import time
from typing import Any, Callable, Dict, List


class Ablation:
    """A small-scale experiment informing a decision."""

    def __init__(self, name: str, variants: Dict[str, Callable],
                 metric: Callable[[Any], float]):
        self.name = name
        self.variants = variants
        self.metric = metric
        self.results: Dict[str, float] = {}
        self.decision: str = ""

    def run(self) -> Dict[str, Any]:
        for vname, fn in self.variants.items():
            self.results[vname] = float(self.metric(fn()))
        best = max(self.results, key=self.results.get)
        self.decision = (f"ablation {self.name}: chose {best} "
                         f"(score {self.results[best]:.3f})")
        return {"name": self.name, "results": self.results,
                "decision": self.decision}


class Checkpoint:
    """A stored checkpoint: config, data manifest, seeds, code revision."""

    def __init__(self, name: str, config: Dict[str, Any],
                 data_manifest: Dict[str, Any], seeds: Dict[str, int],
                 code_revision: str):
        self.name = name
        self.config = config
        self.data_manifest = data_manifest
        self.seeds = seeds
        self.code_revision = code_revision
        self.created_at = time.time()
        self.promoted = False

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "config": self.config,
                "data_manifest": self.data_manifest, "seeds": self.seeds,
                "code_revision": self.code_revision,
                "created_at": self.created_at, "promoted": self.promoted}

    def save(self, path: str):
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, f"{self.name}.json"), "w") as f:
            json.dump(self.to_dict(), f, indent=1, default=str)


class RegressionSuite:
    """Checkpoints are evaluated here; promotion blocked on regression."""

    def __init__(self):
        self.checks: List[Dict[str, Any]] = []

    def add(self, name: str, fn: Callable[[], Dict[str, Any]]):
        self.checks.append({"name": name, "fn": fn})

    def evaluate(self, checkpoint: Checkpoint) -> Dict[str, Any]:
        results = []
        for check in self.checks:
            try:
                out = check["fn"]()
                passed = bool(out.get("passed", False))
            except Exception as e:  # noqa: BLE001
                passed, out = False, {"error": str(e)}
            results.append({"check": check["name"], "passed": passed,
                            "detail": out})
        all_passed = all(r["passed"] for r in results)
        return {"checkpoint": checkpoint.name, "passed": all_passed,
                "results": results,
                "promotion_blocked": not all_passed}


class TestSetGuard:
    """Never tune on the test sets. Test-set IDs are hashed; the guard
    refuses to mark them as training data."""

    def __init__(self, test_ids: List[str]):
        self._test_hashes = {hashlib.sha256(t.encode()).hexdigest()
                             for t in test_ids}

    def check_use(self, item_id: str, purpose: str) -> None:
        h = hashlib.sha256(item_id.encode()).hexdigest()
        if h in self._test_hashes and purpose == "train":
            raise ValueError(
                f"refusing to use test item {item_id!r} for training")

    def is_test(self, item_id: str) -> bool:
        h = hashlib.sha256(item_id.encode()).hexdigest()
        return h in self._test_hashes
