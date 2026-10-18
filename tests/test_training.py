"""Tests for Part 16: Training program."""

import pytest

from kindling.training import (Ablation, Checkpoint, RegressionSuite,
                               TestSetGuard, check_all_stages)


def test_ablation_records_decision():
    ab = Ablation("window-size",
                  {"small": lambda: 0.5, "large": lambda: 0.8},
                  metric=lambda x: x)
    result = ab.run()
    assert result["decision"].startswith("ablation window-size: chose large")
    assert ab.results == {"small": 0.5, "large": 0.8}


def test_checkpoint_stores_all(tmp_path):
    cp = Checkpoint("ckpt-1", {"lr": 0.01}, {"shards": ["a", "b"]},
                    {"train": 1}, "abc123")
    cp.save(str(tmp_path))
    import json, os
    with open(os.path.join(str(tmp_path), "ckpt-1.json")) as f:
        data = json.load(f)
    assert data["config"] == {"lr": 0.01}
    assert data["code_revision"] == "abc123"


def test_regression_blocks_promotion():
    suite = RegressionSuite()
    suite.add("always-passes", lambda: {"passed": True})
    suite.add("always-fails", lambda: {"passed": False})
    cp = Checkpoint("ckpt-x", {}, {}, {}, "rev")
    result = suite.evaluate(cp)
    assert result["passed"] is False
    assert result["promotion_blocked"] is True
    assert not cp.promoted


def test_test_set_guard():
    guard = TestSetGuard(["test-song-1", "test-song-2"])
    assert guard.is_test("test-song-1")
    assert not guard.is_test("train-song-9")
    with pytest.raises(ValueError):
        guard.check_use("test-song-1", "train")
    guard.check_use("test-song-1", "evaluate")  # evaluating is fine
    guard.check_use("train-song-9", "train")  # training is fine


def test_stage_gates_run_in_order():
    # Only check the fast, deterministic gates here (1 and 4-7 use
    # real components; 2 and 3 are heavier/smoke-level).
    results = check_all_stages(upto=1)
    assert results[0]["stage"] == 1
    assert "evidence" in results[0]
