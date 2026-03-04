"""
In-memory job store.
For production, swap this out for Redis or a database.
"""

import time
import threading
from typing import Any


class JobStore:
    def __init__(self):
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create(self, job_id: str, repo_url: str) -> dict:
        job = {
            "job_id": job_id,
            "repo_url": repo_url,
            "status": "queued",
            "progress": 0,
            "logs": [],
            "docs": None,
            "error": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        with self._lock:
            self._jobs[job_id] = job
        return job

    def exists(self, job_id: str) -> bool:
        return job_id in self._jobs

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def update(self, job_id: str, **kwargs) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            for k, v in kwargs.items():
                job[k] = v
            job["updated_at"] = time.time()
            return dict(job)

    def add_log(self, job_id: str, message: str, type_: str = "info"):
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job["logs"].append({
                    "message": message,
                    "type": type_,
                    "ts": time.time(),
                })

    def delete(self, job_id: str):
        with self._lock:
            self._jobs.pop(job_id, None)

    def list_jobs(self) -> list[dict]:
        with self._lock:
            return [dict(j) for j in self._jobs.values()]