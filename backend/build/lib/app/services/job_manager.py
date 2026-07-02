"""A tiny in-process background-job manager for the Data Analysis feature.

CPU-bound SunPy/matplotlib work (sequence fetches, running difference, movies) is
too slow to block an HTTP request, so it runs on a ``ThreadPoolExecutor`` and the
client polls ``GET /api/analysis/jobs/{job_id}`` for progress. This mirrors the
in-memory job registry already used by ``burst_predictor_service`` — fine for the
single-worker backend; a multi-worker deployment would move the registry to Redis.

Job functions receive a ``progress(fraction: float, message: str = "")`` callback
and return either a result path (str/Path) or a ``(path, meta_dict)`` tuple. The
on-disk artifact persists under ``settings.analysis_dir`` even after the job record
is evicted, so a finished result can be re-served or re-requested.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class Job:
    id: str
    state: str = "pending"            # pending | running | done | error
    progress: float = 0.0
    message: str = ""
    result_path: str | None = None
    result_meta: dict[str, Any] | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None


class JobManager:
    def __init__(self, max_workers: int = 2, max_jobs: int = 64) -> None:
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="analysis-job"
        )
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._max_jobs = max_jobs

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
        """Run ``fn(*args, progress=<cb>, **kwargs)`` in the background; return id.

        ``fn`` must accept a ``progress`` keyword and return a result path or a
        ``(path, meta)`` tuple.
        """
        job_id = uuid4().hex
        job = Job(id=job_id)
        with self._lock:
            self._jobs[job_id] = job
            self._evict_locked()

        def _progress(fraction: float, message: str = "") -> None:
            job.progress = max(0.0, min(1.0, float(fraction)))
            if message:
                job.message = message

        def _runner() -> None:
            job.state = "running"
            try:
                result = fn(*args, progress=_progress, **kwargs)
                if isinstance(result, tuple):
                    path, meta = (result + (None,))[:2]
                else:
                    path, meta = result, None
                job.result_path = str(path) if path is not None else None
                job.result_meta = meta
                job.progress = 1.0
                job.state = "done"
            except Exception as exc:  # noqa: BLE001 - report failures via job status
                logger.warning("analysis job %s failed: %s", job_id, exc, exc_info=True)
                job.state = "error"
                job.error = str(exc)
            finally:
                job.finished_at = time.time()

        self._pool.submit(_runner)
        return job_id

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def _evict_locked(self) -> None:
        if len(self._jobs) <= self._max_jobs:
            return
        finished = sorted(
            (j for j in self._jobs.values() if j.state in ("done", "error")),
            key=lambda j: j.finished_at or 0.0,
        )
        for j in finished[: len(self._jobs) - self._max_jobs]:
            self._jobs.pop(j.id, None)


# Module-level singleton used by the analysis services.
job_manager = JobManager()
