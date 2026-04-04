import os
import uuid
import asyncio
import logging
import json
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from agent import DocumentationAgent
from store import JobStore

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# ─── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("DocBuild API starting up...")
    yield
    log.info("DocBuild API shutting down...")

# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="DocBuild API",
    description="Autonomous AI-powered codebase documentation generator",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = JobStore()

# ─── Schemas ──────────────────────────────────────────────────────────────────
class DocumentRequest(BaseModel):
    repo_url: str = Field(description="GitHub repository URL, e.g. https://github.com/owner/repo")
    github_token: str | None = Field(default=None, description="Optional GitHub token for private repos")

# ─── Background task ──────────────────────────────────────────────────────────
async def run_agent_job(job_id: str, repo_url: str, github_token: str | None):
    try:
        store.update(job_id, status="running", progress=2)
        agent = DocumentationAgent(job_id=job_id, repo_url=repo_url, github_token=github_token, store=store)
        docs = await agent.run()
        store.update(job_id, status="done", progress=100, docs=docs)
    except Exception as exc:
        import traceback
        error_msg = str(exc) or repr(exc)
        store.update(job_id, status="error", error=error_msg)
        log.error(f"Job {job_id} Error: {error_msg}")
        log.error(traceback.format_exc())

# ─── JSON API Routes ─────────────────────────────────────────────────────────

@app.post("/api/start-job")
async def start_job(request: DocumentRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    store.create(job_id, request.repo_url)
    background_tasks.add_task(run_agent_job, job_id=job_id, repo_url=request.repo_url, github_token=request.github_token)
    return {"job_id": job_id}


@app.get("/api/job/{job_id}")
def get_job(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job["job_id"],
        "repo_url": job["repo_url"],
        "status": job["status"],
        "progress": job["progress"],
        "logs": job.get("logs", []),
        "error": job.get("error"),
        "created_at": job.get("created_at"),
    }


@app.get("/api/job/{job_id}/stream")
async def job_stream(job_id: str):
    async def sse_generator():
        try:
            while True:
                job = store.get(job_id)
                if not job:
                    yield f"data: {json.dumps({'status': 'not_found', 'error': 'Job not found'})}\n\n"
                    break

                status = job["status"]
                progress = job["progress"]
                logs = job.get("logs", [])

                payload = {
                    "status": status,
                    "progress": progress,
                    "logs": logs[-50:],
                    "error": job.get("error"),
                    "repo_url": job.get("repo_url"),
                }

                if status == "error":
                    yield f"data: {json.dumps(payload)}\n\n"
                    break

                if status == "done":
                    yield f"data: {json.dumps(payload)}\n\n"
                    break

                yield f"data: {json.dumps(payload)}\n\n"
                await asyncio.sleep(0.5)
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'status': 'error', 'error': f'Stream error: {e}'})}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/docs/{job_id}")
def get_docs(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="Documentation not ready yet")
    return job.get("docs", {})
