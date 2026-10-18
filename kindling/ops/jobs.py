"""Job system (18.4): queues, retries, cancellation, progress,
idempotent submission, recovery. A cancelled or failed job never
corrupts the project.
"""

import time
import uuid
from typing import Any, Callable, Dict, List, Optional


class Job:
    def __init__(self, job_id: str, job_type: str, params: Dict[str, Any],
                 idempotency_key: str = None):
        self.id = job_id
        self.type = job_type
        self.params = params
        self.idempotency_key = idempotency_key or job_id
        self.status = "queued"
        self.progress = 0.0
        self.attempts = 0
        self.result: Any = None
        self.error: str = ""
        self.created_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "type": self.type, "status": self.status,
                "progress": round(self.progress, 2),
                "attempts": self.attempts, "error": self.error}


class JobQueue:
    """In-memory job queue with retries and recovery (reference)."""

    def __init__(self, max_retries: int = 3):
        self.jobs: Dict[str, Job] = {}
        self.by_key: Dict[str, str] = {}
        self.max_retries = max_retries
        self.handlers: Dict[str, Callable] = {}

    def register(self, job_type: str, handler: Callable):
        self.handlers[job_type] = handler

    def submit(self, job_type: str, params: Dict[str, Any],
               idempotency_key: str = None) -> Job:
        """Idempotent: same key returns the existing job."""
        key = idempotency_key or f"{job_type}:{uuid.uuid4().hex[:8]}"
        if key in self.by_key:
            return self.jobs[self.by_key[key]]
        job = Job(f"job-{uuid.uuid4().hex[:8]}", job_type, params, key)
        self.jobs[job.id] = job
        self.by_key[key] = job.id
        return job

    def cancel(self, job_id: str) -> Dict[str, Any]:
        job = self.jobs.get(job_id)
        if not job:
            raise KeyError(job_id)
        if job.status in ("queued", "running"):
            job.status = "cancelled"
        return {"id": job_id, "status": job.status}

    def run_next(self) -> Optional[Job]:
        """Run one queued job with retries. Returns the job."""
        for job in self.jobs.values():
            if job.status != "queued":
                continue
            handler = self.handlers.get(job.type)
            if not handler:
                job.status = "failed"
                job.error = f"no handler for {job.type}"
                return job
            job.status = "running"
            while job.attempts <= self.max_retries:
                job.attempts += 1
                try:
                    job.result = handler(job.params,
                                         lambda p: setattr(job, "progress", p))
                    job.status = "done"
                    job.progress = 1.0
                    break
                except Exception as e:  # noqa: BLE001
                    job.error = str(e)
                    if job.attempts > self.max_retries:
                        job.status = "failed"
            return job
        return None

    def recover(self) -> List[str]:
        """After a worker failure: requeue jobs stuck in 'running'.

        A cancelled or failed job never corrupts the project: jobs are
        pure functions of (params); requeueing just reruns them.
        """
        recovered = []
        for job in self.jobs.values():
            if job.status == "running":
                job.status = "queued"
                job.progress = 0.0
                recovered.append(job.id)
        return recovered

    def depth(self) -> int:
        return sum(1 for j in self.jobs.values() if j.status == "queued")
