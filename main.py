"""
DocuForge – FastAPI Backend
Autonomous AI agent that clones a GitHub repo and generates full markdown documentation.
"""

import os
import uuid
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from agent import DocumentationAgent
from store import JobStore

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# ─── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("DocuForge API starting up...")
    yield
    log.info("DocuForge API shutting down...")

# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="DocuForge API",
    description="Autonomous AI-powered codebase documentation generator",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = JobStore()

# ─── Schemas ──────────────────────────────────────────────────────────────────
class DocumentRequest(BaseModel):
    repo_url: str
    github_token: str | None = None

class JobStatusResponse(BaseModel):
    job_id: str
    status: str        # queued | running | done | error
    progress: int
    repo_url: str

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "docuforge"}


@app.post("/api/document", response_model=dict, status_code=202)
async def create_documentation_job(
    req: DocumentRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start an asynchronous documentation job.
    Returns a job_id immediately; poll /api/stream/{job_id} for SSE updates.
    """
    job_id = str(uuid.uuid4())
    store.create(job_id, req.repo_url)

    background_tasks.add_task(
        run_agent_job,
        job_id=job_id,
        repo_url=req.repo_url,
        github_token=req.github_token,
    )

    log.info(f"Job {job_id} queued for {req.repo_url}")
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/stream/{job_id}")
async def stream_job(job_id: str):
    """
    SSE endpoint. Emits real-time agent log events and a final `done` event
    containing the complete documentation JSON.
    """
    if not store.exists(job_id):
        raise HTTPException(status_code=404, detail="Job not found")

    return StreamingResponse(
        event_generator(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/jobs/{job_id}", response_model=dict)
async def get_job(job_id: str):
    """Return the current state (+ docs if done) of a job."""
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/jobs/{job_id}/docs", response_model=dict)
async def get_docs(job_id: str):
    """Return only the generated docs for a completed job."""
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "done":
        raise HTTPException(status_code=202, detail=f"Job status: {job['status']}")
    return job.get("docs", {})


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    """Clean up a job and its cloned repo from disk."""
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    store.delete(job_id)
    return {"deleted": job_id}


# ─── Background task ──────────────────────────────────────────────────────────

async def run_agent_job(job_id: str, repo_url: str, github_token: str | None):
    """Run the full agent pipeline in the background, writing results to store."""
    try:
        store.update(job_id, status="running", progress=2)
        agent = DocumentationAgent(
            job_id=job_id,
            repo_url=repo_url,
            github_token=github_token,
            store=store,
        )
        docs = await agent.run()
        store.update(job_id, status="done", progress=100, docs=docs)
        log.info(f"Job {job_id} completed successfully")
    except Exception as exc:
        log.exception(f"Job {job_id} failed: {exc}")
        store.update(job_id, status="error", error=str(exc))


# ─── SSE generator ────────────────────────────────────────────────────────────

async def event_generator(job_id: str) -> AsyncGenerator[str, None]:
    """
    Yields SSE frames by tailing the job's log queue.
    Terminates once the job reaches done/error status.
    """
    sent_index = 0

    while True:
        job = store.get(job_id)
        if not job:
            yield _sse("error", {"message": "Job not found"})
            break

        logs = job.get("logs", [])
        new_logs = logs[sent_index:]
        for entry in new_logs:
            yield _sse("log", entry)
        sent_index += len(new_logs)

        # Progress heartbeat
        yield _sse("progress", {"progress": job.get("progress", 0)})

        if job["status"] == "done":
            yield _sse("done", {"docs": job.get("docs", {}), "progress": 100})
            break

        if job["status"] == "error":
            yield _sse("error", {"message": job.get("error", "Unknown error")})
            break

        await asyncio.sleep(0.4)


def _sse(event: str, data: dict) -> str:
    import json
    payload = json.dumps(data)
    return f"event: {event}\ndata: {payload}\n\n"
