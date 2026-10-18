"""Tests for Part 18: Deployment and operations."""

import numpy as np
import pytest

from kindling.ops import (AccessControl, JobQueue, Monitor, staged_render,
                          tier_for)


def test_job_idempotent_submit():
    q = JobQueue()
    q.register("render", lambda params, progress: {"ok": True})
    a = q.submit("render", {"seed": 1}, idempotency_key="k1")
    b = q.submit("render", {"seed": 1}, idempotency_key="k1")
    assert a.id == b.id
    assert q.depth() == 1


def test_job_retry_and_recovery():
    q = JobQueue(max_retries=2)
    calls = []
    def flaky(params, progress):
        calls.append(1)
        if len(calls) < 2:
            raise RuntimeError("boom")
        return {"ok": True}
    q.register("render", flaky)
    job = q.submit("render", {})
    done = q.run_next()
    assert done.status == "done"
    assert done.attempts == 2


def test_job_cancel():
    q = JobQueue()
    job = q.submit("render", {})
    out = q.cancel(job.id)
    assert out["status"] == "cancelled"


def test_worker_failure_recovery():
    q = JobQueue()
    q.register("render", lambda params, progress: {"ok": True})
    job = q.submit("render", {})
    job.status = "running"  # simulate a killed worker
    recovered = q.recover()
    assert recovered == [job.id]
    assert q.jobs[job.id].status == "queued"
    # Rerun succeeds; project never corrupted (pure function of params).
    done = q.run_next()
    assert done.status == "done"


def test_staged_results():
    def render_fn(stage, params):
        return np.zeros(100) * len(stage)
    stages = list(staged_render(render_fn, {}))
    assert [s for s, _ in stages] == ["sketch", "draft", "final"]


def test_tier_selection():
    assert tier_for(10, "draft") == "draft"
    assert tier_for(60, "draft") == "studio"  # upgraded for length
    assert tier_for(10, "hosted") == "hosted"  # never downgraded
    with pytest.raises(ValueError):
        tier_for(10, "bogus")


def test_monitor():
    m = Monitor()
    m.record_latency("render", 1.2)
    m.record_latency("render", 1.4)
    m.record_crash()
    m.record_cost(0.02)
    s = m.summary()
    assert s["latency_p50_by_stage"]["render"] == 1.3
    assert s["crashes"] == 1


def test_access_control_and_audit():
    ac = AccessControl()
    ac.grant("user1", "project:song", ["read", "write"])
    assert ac.check("user1", "project:song", "read") is True
    assert ac.check("user1", "project:song", "delete") is False
    # Voice access is always logged.
    ac.grant("user1", "voice:mara", ["render"])
    ac.check("user1", "voice:mara", "render")
    assert any(e["resource"] == "voice:mara" for e in ac.audit_log)
    # Rate limiting.
    for _ in range(60):
        assert ac.rate_limit("user1", max_per_minute=60) is True
    assert ac.rate_limit("user1", max_per_minute=60) is False
