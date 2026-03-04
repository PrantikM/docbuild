

import os
import json
import asyncio
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Any

import anthropic

from store import JobStore

log = logging.getLogger(__name__)

WORK_DIR = Path(os.getenv("WORK_DIR", "/tmp/docuforge"))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-20250514"
MAX_ITERATIONS = 20
MAX_FILE_CHARS = 8_000      # truncate large files
MAX_TREE_FILES = 300        # cap tree size sent to model

# ─── Tool definitions ─────────────────────────────────────────────────────────
TOOLS: list[dict] = [
    {
        "name": "read_file",
        "description": (
            "Read the full text content of a file in the cloned repository. "
            "Use this to understand code, configuration, and existing docs. "
            "Binary files return an error message."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path relative to the repository root."
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "list_directory",
        "description": (
            "List the files and immediate sub-directories inside a directory. "
            "Pass an empty string to list the repository root."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path relative to the repository root ('' for root)."
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "search_files",
        "description": (
            "Search for a keyword or pattern across all text files in the repo. "
            "Returns matching file paths with a short excerpt."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "The search term (case-insensitive)."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of matches to return (default 10).",
                    "default": 10
                }
            },
            "required": ["keyword"]
        }
    },
    {
        "name": "finish_documentation",
        "description": (
            "Call this once you have gathered enough information to write comprehensive "
            "documentation. Provide ALL fields with full markdown content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "main_readme": {
                    "type": "string",
                    "description": "Complete main README.md in Markdown — project overview, features, tech stack, badges."
                },
                "how_to_run": {
                    "type": "string",
                    "description": "Step-by-step how-to-run guide: prerequisites, installation, env vars, running locally, running tests, Docker."
                },
                "architecture_doc": {
                    "type": "string",
                    "description": "Architecture & dependency overview: directory structure, component diagram (ASCII/Mermaid), data-flow, key design decisions."
                },
                "api_reference": {
                    "type": "string",
                    "description": "API / module reference in Markdown. Include endpoints, parameters, response shapes, or exported functions. Leave empty string if not applicable."
                },
                "folder_readmes": {
                    "type": "array",
                    "description": "One README per significant folder/module.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "folder": {"type": "string", "description": "Folder path relative to repo root."},
                            "content": {"type": "string", "description": "Markdown README content for this folder."}
                        },
                        "required": ["folder", "content"]
                    }
                },
                "contributing_guide": {
                    "type": "string",
                    "description": "CONTRIBUTING.md content: branching strategy, PR process, code style, testing expectations."
                },
                "changelog": {
                    "type": "string",
                    "description": "Inferred CHANGELOG.md based on commit history patterns or existing changelog. Empty string if not applicable."
                }
            },
            "required": [
                "main_readme",
                "how_to_run",
                "architecture_doc",
                "folder_readmes"
            ]
        }
    }
]


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
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # ── public ────────────────────────────────────────────────────────────────

    async def run(self) -> dict:
        try:
            self._log("🚀 Starting documentation agent...", "system")
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
        # Prevent path traversal
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

    # ── tool dispatch ─────────────────────────────────────────────────────────

    def _dispatch_tool(self, name: str, inputs: dict) -> str:
        if name == "read_file":
            path = inputs["path"]
            self._log(f"📖 read_file({path})", "tool")
            return self._read_file(path)

        if name == "list_directory":
            path = inputs.get("path", "")
            self._log(f"📁 list_directory({path or '/'})", "tool")
            return self._list_directory(path)

        if name == "search_files":
            kw = inputs["keyword"]
            mx = inputs.get("max_results", 10)
            self._log(f"🔍 search_files('{kw}')", "tool")
            return self._search_files(kw, mx)

        return f"[Unknown tool: {name}]"

    # ── agent loop ────────────────────────────────────────────────────────────

    async def _agent_loop(self, tree: list[str]) -> dict:
        tree_str = "\n".join(tree)
        system = f"""You are DocuForge, an expert software documentation agent.

Your mission: thoroughly explore this repository and produce world-class documentation.

## Strategy (follow this order)
1. **Identify project type** — read package.json / requirements.txt / Cargo.toml / go.mod / pom.xml / build.gradle etc.
2. **Read existing docs** — README, CONTRIBUTING, docs/, wiki/ if present.
3. **Understand structure** — list_directory on root, then key subdirectories.
4. **Read entry points** — main.py, index.js, app.py, cmd/, server.go, etc.
5. **Sample key modules** — read 3-5 representative source files per major component.
6. **Understand config** — .env.example, docker-compose.yml, Makefile, CI configs.
7. **Infer dependencies** — parse dependency files for libraries and their purposes.
8. Once you have sufficient understanding, call `finish_documentation`.

## Quality bar
- Documentation must be professional, complete, and immediately useful.
- Include real file paths, actual command examples from the repo.
- Architecture doc must include ASCII directory tree and component relationships.
- How-to-run must cover: prerequisites, installation, env setup, run, test, Docker/deploy.
- Every folder README must explain purpose, key files, and how it fits the whole.

## Repository file tree
```
{tree_str}
```
"""

        messages: list[dict] = [
            {
                "role": "user",
                "content": (
                    f"Please document the repository at {self.repo_url}. "
                    "Start by identifying the project type, then explore systematically. "
                    "Be thorough — read real files before writing anything."
                )
            }
        ]

        iterations = 0

        while iterations < MAX_ITERATIONS:
            iterations += 1
            self._log(f"🤖 Agent iteration {iterations}/{MAX_ITERATIONS}", "system")

            # Run sync Anthropic call in thread pool to not block event loop
            response = await asyncio.to_thread(
                self.client.messages.create,
                model=MODEL,
                max_tokens=8192,
                system=system,
                tools=TOOLS,
                messages=messages,
            )

            # Append assistant turn
            messages.append({"role": "assistant", "content": response.content})

            stop = response.stop_reason

            if stop == "end_turn":
                self._log("Agent finished without calling finish_documentation — forcing it", "system")
                messages.append({
                    "role": "user",
                    "content": "You've gathered enough information. Now call finish_documentation with everything."
                })
                continue

            if stop != "tool_use":
                break

            # Process tool calls
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            tool_results = []

            for tu in tool_uses:
                if tu.name == "finish_documentation":
                    self._log("✅ Documentation complete!", "success")
                    self._progress(95)
                    return tu.input   # ← final output

                result = self._dispatch_tool(tu.name, tu.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": result,
                })

            messages.append({"role": "user", "content": tool_results})

            # Update progress (roughly 20–90 over MAX_ITERATIONS)
            pct = 20 + int((iterations / MAX_ITERATIONS) * 70)
            self._progress(pct)

        # Fallback: force finish
        self._log("⚡ Max iterations reached — forcing documentation generation", "system")
        messages.append({
            "role": "user",
            "content": (
                "You must now call finish_documentation immediately with everything you've learned. "
                "Do not read any more files."
            )
        })

        response = await asyncio.to_thread(
            self.client.messages.create,
            model=MODEL,
            max_tokens=8192,
            system=system,
            tools=TOOLS,
            tool_choice={"type": "any"},
            messages=messages,
        )

        for block in response.content:
            if hasattr(block, "name") and block.name == "finish_documentation":
                return block.input

        raise RuntimeError("Agent failed to call finish_documentation")

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