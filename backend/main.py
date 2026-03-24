import os
import uuid
import asyncio
import logging
import json
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Annotated

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from pydantic import BaseModel, Field

from fastui import FastUI, AnyComponent, prebuilt_html, components as c
from fastui.components.display import DisplayMode, DisplayLookup
from fastui.events import GoToEvent, PageEvent
from fastui.forms import fastui_form

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
class DocumentRequestForm(BaseModel):
    repo_url: str = Field(title="GitHub Repository URL", description="e.g., https://github.com/owner/repo")
    github_token: str | None = Field(default=None, title="GitHub Token", description="Optional. Required for private repos.")

# ─── Background task ──────────────────────────────────────────────────────────
async def run_agent_job(job_id: str, repo_url: str, github_token: str | None):
    try:
        store.update(job_id, status="running", progress=2)
        agent = DocumentationAgent(job_id=job_id, repo_url=repo_url, github_token=github_token, store=store)
        docs = await agent.run()
        store.update(job_id, status="done", progress=100, docs=docs)
    except Exception as exc:
        store.update(job_id, status="error", error=str(exc))
        log.error(f"Job {job_id} Error: {exc}")

# ─── FastUI Routes ────────────────────────────────────────────────────────────

def shared_page(*components: AnyComponent, title: str = "DocBuild") -> list[AnyComponent]:
    return [
        c.PageTitle(text=title),
        c.Navbar(title="DocBuild ◈", title_event=GoToEvent(url="/")),
        c.Page(components=list(components)),
    ]

@app.get("/api", response_model=FastUI, response_model_exclude_none=True)
@app.get("/api/", response_model=FastUI, response_model_exclude_none=True)
def index():
    return shared_page(
        c.Heading(text="Document any codebase, autonomously", level=2),
        c.Paragraph(text="Point DocBuild at a GitHub repo. The LangGraph agent clones it and writes complete documentation."),
        c.ModelForm(
            model=DocumentRequestForm,
            submit_url="/api/start-job",
        )
    )

@app.post("/api/start-job", response_model=FastUI, response_model_exclude_none=True)
@app.post("/api/start-job/", response_model=FastUI, response_model_exclude_none=True)
async def start_job(background_tasks: BackgroundTasks, form: Annotated[DocumentRequestForm, fastui_form(DocumentRequestForm)]):
    job_id = str(uuid.uuid4())
    store.create(job_id, form.repo_url)
    background_tasks.add_task(run_agent_job, job_id=job_id, repo_url=form.repo_url, github_token=form.github_token)
    return [c.FireEvent(event=GoToEvent(url=f"/job/{job_id}"))]


@app.get("/api/job/{job_id}", response_model=FastUI, response_model_exclude_none=True)
def job_page(job_id: str):
    job = store.get(job_id)
    if not job:
        return shared_page(c.Heading(text="Job Not Found", level=2), c.Button(text="Back to Home", on_click=GoToEvent(url="/")))
    
    return shared_page(
        c.Heading(text=f"Processing: {job['repo_url']}", level=2),
        c.ServerLoad(
            path=f"/api/job/{job_id}/stream",
            sse=True,
            load_trigger=PageEvent(name='load'),
        )
    )

@app.get("/api/job/{job_id}/stream")
async def job_stream(job_id: str):
    async def sse_generator():
        while True:
            job = store.get(job_id)
            if not job:
                yield f"data: {FastUI(root=[c.Text(text='Job not found')]).model_dump_json(by_alias=True, exclude_none=True)}\n\n"
                break

            status = job["status"]
            progress = job["progress"]
            logs = job.get("logs", [])
            
            log_text = "\n".join([f"[{time.strftime('%H:%M:%S', time.localtime(l.get('ts', time.time())))}] {l.get('message')}" for l in logs[-50:]])
            
            ui = [
                c.Heading(text=f"Status: {status.upper()} ({progress}%)", level=3),
                c.Progress(value=progress / 100) if progress < 100 else c.Text(text=""),
            ]
            
            if status == "error":
                ui.append(c.Heading(text=f"Error: {job.get('error')}", level=4))
                ui.append(c.Button(text="Try Again", on_click=GoToEvent(url="/")))
                yield f"data: {FastUI(root=ui).model_dump_json(by_alias=True, exclude_none=True)}\n\n"
                break
                
            if status == "done":
                ui.append(c.Button(text="View Documentation", on_click=GoToEvent(url=f"/docs/{job_id}")))
                yield f"data: {FastUI(root=ui).model_dump_json(by_alias=True, exclude_none=True)}\n\n"
                break

            ui.append(c.Markdown(text=f"```text\n{log_text}\n```"))

            yield f"data: {FastUI(root=ui).model_dump_json(by_alias=True, exclude_none=True)}\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(sse_generator(), media_type="text/event-stream")

@app.get("/api/docs/{job_id}", response_model=FastUI, response_model_exclude_none=True)
def docs_page(job_id: str):
    job = store.get(job_id)
    if not job or job["status"] != "done":
        return shared_page(c.Heading(text="Docs not ready or job not found.", level=2), c.Button(text="Back", on_click=GoToEvent(url="/")))
    
    docs = job.get("docs", {})
    return shared_page(
        c.Heading(text=f"Documentation Results: {job['repo_url']}", level=2),
        c.Markdown(text=docs.get("main_readme", "")), 
        c.Divider(),
        c.Heading(text="Architecture Details", level=3),
        c.Markdown(text=docs.get("architecture_doc", "")),
        c.Divider(),
        c.Heading(text="How to Run", level=3),
        c.Markdown(text=docs.get("how_to_run", "")),
        c.Divider(),
        c.Button(text="View Raw JSON Response", on_click=GoToEvent(url=f"/api/jobs/{job_id}/docs_raw")),
        c.Button(text="Start New Job", on_click=GoToEvent(url="/"))
    )


@app.get("/api/jobs/{job_id}/docs_raw")
async def get_raw_docs(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.get("docs", {})

# ─── Catch-all for routing FastUI React frontend ────────────────────────────
@app.get("/{path:path}")
async def html_landing() -> HTMLResponse:
    # Serve the pre-built HTML from fastui to power the frontend single-page-app
    # prebuilt_html defaults to fetching components from `/api`
    return HTMLResponse(prebuilt_html(title='DocBuild AI'))
