import os
import json
import asyncio
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Any, Annotated, Sequence, TypedDict

from store import JobStore
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

import tempfile
WORK_DIR = Path(os.getenv("WORK_DIR", os.path.join(tempfile.gettempdir(), "docbuild")))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

MAX_ITERATIONS = 20
MAX_FILE_CHARS = 8_000      # truncate large files
MAX_TREE_FILES = 300        # cap tree size sent to model

# ─── Pydantic schemas for the final documentation ────────────────────────────
class FolderReadme(BaseModel):
    folder: str = Field(description="Folder path relative to repo root.")
    content: str = Field(description="Markdown README content for this folder.")

class FinishDocumentation(BaseModel):
    """Call this once you have gathered enough information to write comprehensive documentation."""
    main_readme: str = Field(description="Complete main README.md in Markdown — project overview, features, tech stack, badges.")
    how_to_run: str = Field(description="Step-by-step how-to-run guide: prerequisites, installation, env vars, running locally, running tests, Docker.")
    architecture_doc: str = Field(description="Architecture & dependency overview: directory structure, component diagram (ASCII/Mermaid), data-flow, key design decisions.")
    api_reference: str = Field(description="API / module reference in Markdown. Include endpoints, parameters, response shapes, or exported functions. Leave empty string if not applicable.", default="")
    folder_readmes: list[FolderReadme] = Field(description="One README per significant folder/module.")
    contributing_guide: str = Field(description="CONTRIBUTING.md content: branching strategy, PR process, code style, testing expectations.", default="")
    changelog: str = Field(description="Inferred CHANGELOG.md based on commit history patterns. Empty string if not applicable.", default="")


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    docs: dict | None
    iterations: int

# ─── Agent ────────────────────────────────────────────────────────────────────
class DocumentationAgent:
    def __init__(
        self,
        job_id: str,
        repo_url: str,
        github_token: str | None,
        store: JobStore,
    ):
        self.job_id = job_id
        self.repo_url = repo_url
        self.github_token = github_token
        self.store = store
        self.repo_dir: Path | None = None
        self.llm = ChatAnthropic(
            model_name="claude-3-5-sonnet-20240620", 
            temperature=0, 
            max_tokens=8192,
            api_key=ANTHROPIC_API_KEY or None
        )

    # ── public ────────────────────────────────────────────────────────────────

    async def run(self) -> dict:
        try:
            self._log("🚀 Starting documentation agent with LangGraph...", "system")
            await self._clone_repo()
            self._progress(15)

            tree = self._build_tree()
            self._log(f"📂 Repository has {len(tree)} files", "system")
            self._progress(20)

            docs = await self._agent_loop(tree)
            return docs
        finally:
            self._cleanup()

    # ── cloning ───────────────────────────────────────────────────────────────

    async def _clone_repo(self):
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        self.repo_dir = WORK_DIR / self.job_id

        clone_url = self.repo_url
        if self.github_token:
            # Inject token into HTTPS URL
            clone_url = clone_url.replace(
                "https://", f"https://{self.github_token}@"
            )

        self._log(f"📥 Cloning {self.repo_url}...", "system")

        proc = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth=1", "--single-branch",
            clone_url, str(self.repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err = stderr.decode()[:500]
            raise RuntimeError(f"git clone failed: {err}")

        self._log("✅ Repository cloned successfully", "system")

    # ── file helpers ──────────────────────────────────────────────────────────

    def _build_tree(self) -> list[str]:
        """Return sorted list of all relative file paths."""
        files = []
        for p in self.repo_dir.rglob("*"):
            if p.is_file() and not self._is_ignored(p):
                files.append(str(p.relative_to(self.repo_dir)))
        return sorted(files)[:MAX_TREE_FILES]

    @staticmethod
    def _is_ignored(path: Path) -> bool:
        ignored = {
            ".git", "node_modules", "__pycache__", ".venv", "venv",
            ".env", "dist", "build", ".next", ".nuxt", "coverage",
            ".pytest_cache", ".mypy_cache", ".ruff_cache",
        }
        return any(part in ignored for part in path.parts)

    def _read_file(self, rel_path: str) -> str:
        target = (self.repo_dir / rel_path).resolve()
        if not str(target).startswith(str(self.repo_dir)):
            return "[Error: path traversal detected]"
        if not target.exists():
            return f"[Error: file not found: {rel_path}]"
        if not target.is_file():
            return f"[Error: not a file: {rel_path}]"
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
            if len(text) > MAX_FILE_CHARS:
                text = text[:MAX_FILE_CHARS] + f"\n\n... [truncated — {len(text)} total chars]"
            return text
        except Exception as exc:
            return f"[Error reading file: {exc}]"

    def _list_directory(self, rel_path: str) -> str:
        target = (self.repo_dir / rel_path).resolve() if rel_path else self.repo_dir.resolve()
        if not str(target).startswith(str(self.repo_dir)):
            return "[Error: path traversal detected]"
        if not target.is_dir():
            return f"[Error: not a directory: {rel_path}]"
        entries = []
        for item in sorted(target.iterdir()):
            if self._is_ignored(item):
                continue
            suffix = "/" if item.is_dir() else ""
            entries.append(str(item.relative_to(self.repo_dir)) + suffix)
        return "\n".join(entries) if entries else "(empty directory)"

    def _search_files(self, keyword: str, max_results: int = 10) -> str:
        keyword_lower = keyword.lower()
        results = []
        for p in self.repo_dir.rglob("*"):
            if not p.is_file() or self._is_ignored(p):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                idx = text.lower().find(keyword_lower)
                if idx != -1:
                    start = max(0, idx - 60)
                    excerpt = text[start:idx + len(keyword) + 60].replace("\n", " ")
                    rel = str(p.relative_to(self.repo_dir))
                    results.append(f"{rel}: ...{excerpt}...")
                    if len(results) >= max_results:
                        break
            except Exception:
                pass
        return "\n".join(results) if results else "(no matches found)"


    # ── agent loop ────────────────────────────────────────────────────────────

    async def _agent_loop(self, tree: list[str]) -> dict:
        @tool
        def read_file(path: str) -> str:
            """Read the full text content of a file in the cloned repository."""
            self._log(f"📖 read_file({path})", "tool")
            return self._read_file(path)

        @tool
        def list_directory(path: str) -> str:
            """List the files and immediate sub-directories inside a directory. Pass empty string for root."""
            self._log(f"📁 list_directory({path or '/'})", "tool")
            return self._list_directory(path)

        @tool
        def search_files(keyword: str, max_results: int = 10) -> str:
            """Search for a keyword or pattern across all text files in the repo."""
            self._log(f"🔍 search_files('{keyword}')", "tool")
            return self._search_files(keyword, max_results)

        tools = [read_file, list_directory, search_files]
        llm_with_tools = self.llm.bind_tools(tools + [FinishDocumentation])

        async def call_model(state: AgentState):
            self._log(f"🤖 Agent iteration {state['iterations']}/{MAX_ITERATIONS}", "system")
            response = await llm_with_tools.ainvoke(state["messages"])
            # Update progress linearly (roughly 20-90 over max_iterations)
            pct = 20 + int((state["iterations"] / MAX_ITERATIONS) * 70)
            self._progress(pct)
            return {"messages": [response], "iterations": state["iterations"] + 1}

        async def process_tools(state: AgentState):
            last_message = state["messages"][-1]
            tool_messages = []
            
            for tc in last_message.tool_calls:
                if tc["name"] == "FinishDocumentation":
                    self._log("✅ Documentation complete!", "success")
                    self._progress(95)
                    # Store docs to signal completion to should_continue
                    return {"docs": tc["args"]}
                
                # Execute normal tool
                if tc["name"] == "read_file":
                    result = read_file.invoke(tc["args"])
                elif tc["name"] == "list_directory":
                    result = list_directory.invoke(tc["args"])
                elif tc["name"] == "search_files":
                    result = search_files.invoke(tc["args"])
                else:
                    result = f"[Unknown tool: {tc['name']}]"
                    
                tool_messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))
                
            return {"messages": tool_messages}

        def should_continue(state: AgentState) -> str:
            if state.get("docs") is not None:
                return END
            if state["iterations"] >= MAX_ITERATIONS:
                return "force_finish"
            last_message = state["messages"][-1]
            if last_message.tool_calls:
                return "tools"
            return "agent"

        async def force_finish(state: AgentState):
            self._log("⚡ Max iterations reached — forcing documentation generation", "system")
            forced_msg = HumanMessage(content="You must now call FinishDocumentation immediately with everything you've learned. Do not read any more files.")
            final_llm = self.llm.bind_tools([FinishDocumentation], tool_choice="FinishDocumentation")
            response = await final_llm.ainvoke(state["messages"] + [forced_msg])
            
            docs = {}
            for tc in response.tool_calls:
                if tc["name"] == "FinishDocumentation":
                    docs = tc["args"]
                    break
            
            return {"docs": docs}

        workflow = StateGraph(AgentState)
        workflow.add_node("agent", call_model)
        workflow.add_node("tools", process_tools)
        workflow.add_node("force_finish", force_finish)

        workflow.set_entry_point("agent")
        workflow.add_conditional_edges("agent", should_continue)
        workflow.add_edge("tools", "agent")
        workflow.add_edge("force_finish", END)

        app = workflow.compile()

        tree_str = "\n".join(tree)
        system_msg = SystemMessage(content=f"""You are DocBuild, an expert software documentation agent.

Your mission: thoroughly explore this repository and produce world-class documentation.

## Strategy (follow this order)
1. **Identify project type** — read package.json / requirements.txt / Cargo.toml / go.mod / pom.xml / build.gradle etc.
2. **Read existing docs** — README, CONTRIBUTING, docs/, wiki/ if present.
3. **Understand structure** — list_directory on root, then key subdirectories.
4. **Read entry points** — main.py, index.js, app.py, cmd/, server.go, etc.
5. **Sample key modules** — read 3-5 representative source files per major component.
6. **Understand config** — .env.example, docker-compose.yml, Makefile, CI configs.
7. **Infer dependencies** — parse dependency files for libraries and their purposes.
8. Once you have sufficient understanding, call `FinishDocumentation`.

## Quality bar
- Documentation must be professional, complete, and immediately useful.
- Include real file paths, actual command examples from the repo.
- Architecture doc must include ASCII directory tree and component relationships.
- How-to-run must cover: prerequisites, installation, env setup, run, test, Docker/deploy.
- Every folder README must explain purpose, key files, and how it fits the whole.

## Repository file tree
```
{tree_str}
```""")

        initial_state = {
            "messages": [
                system_msg, 
                HumanMessage(content=f"Please document the repository at {self.repo_url}. Be thorough — read real files before writing anything.")
            ],
            "docs": None,
            "iterations": 0
        }

        final_state = await app.ainvoke(initial_state)
        
        if final_state.get("docs"):
            return final_state["docs"]
        raise RuntimeError("Agent failed to call FinishDocumentation")

    # ── helpers ───────────────────────────────────────────────────────────────

    def _log(self, message: str, type_: str = "info"):
        self.store.add_log(self.job_id, message, type_)
        log.info(f"[{self.job_id[:8]}] {message}")

    def _progress(self, pct: int):
        self.store.update(self.job_id, progress=pct)

    def _cleanup(self):
        if self.repo_dir and self.repo_dir.exists():
            shutil.rmtree(self.repo_dir, ignore_errors=True)
            log.info(f"Cleaned up {self.repo_dir}")