# 🏗️ DocBuild

> **Autonomous AI documentation generator for any GitHub repository.**

Point DocBuild at any public (or private) GitHub repo and it will autonomously clone it, explore the codebase, and produce world-class documentation — all without any manual input.

Powered by a **LangGraph agentic loop** running **Claude claude-3-5-sonnet**, served through a **FastAPI** backend with a **React** frontend.

---

## ✨ What It Generates

For any repository, DocBuild produces:

| Output | Description |
|--------|-------------|
| `README.md` | Full project overview, features, tech stack |
| `HOW_TO_RUN.md` | Prerequisites, installation, env vars, Docker |
| `ARCHITECTURE.md` | Directory structure, ASCII/Mermaid component diagrams, data-flow |
| `API_REFERENCE.md` | Endpoints, parameters, response shapes (if applicable) |
| `CONTRIBUTING.md` | Branching strategy, PR process, code style |
| `CHANGELOG.md` | Inferred from commit history patterns |
| Folder READMEs | One per significant module/folder |

---

## 🚀 How It Works

```
User submits GitHub URL
        │
        ▼
 FastAPI creates a Job (UUID)
        │
        ▼
 Background Task: DocumentationAgent.run()
        │
        ├── git clone --depth=1 <repo>
        │
        ├── Build file tree (up to 300 files)
        │
        └── LangGraph Agent Loop (up to 20 iterations)
                │
                ├── read_file(path)       ← Tool
                ├── list_directory(path)  ← Tool
                ├── search_files(keyword) ← Tool
                │
                └── FinishDocumentation() ← Final structured output
                        │
                        ▼
              Docs saved to JobStore
                        │
                        ▼
              SSE stream → React frontend renders results
```

The agent follows a structured strategy: it first identifies the project type (reading `package.json`, `requirements.txt`, etc.), reads existing docs, explores directory structure, reads entry points and key modules, inspects config files, and only then writes the documentation.

---

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Web Framework | [FastAPI](https://fastapi.tiangolo.com/) |
| Frontend | [React](https://react.dev/) + [Vite](https://vitejs.dev/) SPA |
| AI Agent | [LangGraph](https://langchain-ai.github.io/langgraph/) state machine |
| LLM | [Anthropic Claude](https://www.anthropic.com/) (`claude-3-5-sonnet-20240620`) |
| LLM Client | `langchain-anthropic` |
| Job State | In-memory `JobStore` (thread-safe) |
| Streaming | Server-Sent Events (SSE) via FastAPI `StreamingResponse` |
| Data Validation | [Pydantic](https://docs.pydantic.dev/) v2 |
| Markdown Rendering | `react-markdown` + `remark-gfm` + `rehype-highlight` |
| Routing | `react-router-dom` v7 |
| Async | Python `asyncio` + `asyncio.create_subprocess_exec` |

---

## 📁 Project Structure

```
docbuild/
├── backend/
│   ├── main.py          # FastAPI app, JSON API routes, SSE streaming
│   ├── agent.py         # LangGraph DocumentationAgent — cloning, tools, agent loop
│   ├── store.py         # Thread-safe in-memory JobStore
│   └── requirements.txt # Python dependencies
└── frontend/
    ├── index.html       # Root HTML with Google Fonts
    ├── package.json     # Node.js dependencies
    ├── vite.config.js   # Vite config with API proxy
    └── src/
        ├── main.jsx     # React entry point
        ├── App.jsx      # Root component with routing
        ├── index.css    # Design system (dark mode, glassmorphism)
        ├── api.js       # API client functions
        ├── components/
        │   └── Navbar.jsx
        └── pages/
            ├── HomePage.jsx  # Repo URL form + hero section
            ├── JobPage.jsx   # SSE-powered live job tracking
            └── DocsPage.jsx  # Tabbed markdown doc viewer
```

---

## ⚙️ Setup & Installation

### 1. Clone the repository

```bash
git clone https://github.com/PrantikM/docbuild.git
cd docbuild
```

### 2. Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Frontend setup

```bash
cd frontend
npm install
```

### 4. Set environment variables

```bash
export ANTHROPIC_API_KEY="your_anthropic_api_key_here"
export WORK_DIR="/tmp/docbuild"   # Optional — defaults to system temp dir
```

On Windows:
```cmd
set ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

> Get an Anthropic API key at [https://console.anthropic.com](https://console.anthropic.com)

### 5. Run the app

**Terminal 1 — Backend:**
```bash
cd backend
uvicorn main:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

The frontend will be available at `http://localhost:5173` and automatically proxies API requests to the backend on port 8000.

---

## 🖥️ Usage

1. Open `http://localhost:5173` in your browser.
2. Enter a GitHub repository URL (e.g. `https://github.com/owner/repo`).
3. Optionally provide a GitHub token for private repositories.
4. Click **Generate Documentation** — the agent starts running in the background.
5. Watch real-time logs stream in as the agent explores the codebase.
6. Once complete, click **View Documentation** to see the full generated output.

---

## 🔌 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/start-job` | Submit a repo URL (JSON body), creates a new job |
| `GET` | `/api/job/{job_id}` | Job status as JSON |
| `GET` | `/api/job/{job_id}/stream` | SSE stream of real-time job progress & logs |
| `GET` | `/api/docs/{job_id}` | Generated documentation as JSON |

### Example: Submit a job via curl

```bash
curl -X POST http://localhost:8000/api/start-job \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/owner/repo", "github_token": null}'
```

---

## 🧩 Key Design Decisions

**LangGraph state machine** — The agent is modelled as a graph with `agent → tools → agent` cycles, a `force_finish` fallback node if max iterations are hit, and a clean `END` state once `FinishDocumentation` is called.

**Structured output via Pydantic** — `FinishDocumentation` is a Pydantic model bound as a tool to the LLM, ensuring the final output always conforms to the expected schema (main README, how-to-run, architecture doc, folder READMEs, etc.).

**Decoupled frontend** — The React SPA communicates with the backend via a clean JSON API. In development, Vite proxies `/api` requests to the backend. In production, both can be served behind a reverse proxy.

**Path traversal protection** — `_read_file` and `_list_directory` resolve paths and verify they stay within the cloned repo directory before reading.

**Auto-cleanup** — The cloned repo is deleted from disk in the `finally` block of `agent.run()`, regardless of success or failure.

**In-memory store** — `JobStore` uses a `threading.Lock` for safe concurrent access. The code comment explicitly notes this should be swapped for Redis or a database in production.

---

## 🔐 Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | ✅ Yes | — | Your Anthropic API key |
| `WORK_DIR` | ❌ No | System temp dir | Where repos are cloned during processing |

---

## 📌 Requirements

- Python 3.11+
- Node.js 18+
- `git` installed and available on `PATH`
- A valid [Anthropic API key](https://console.anthropic.com)

---

## 🔮 Production Considerations

- Swap `JobStore` (in-memory) for **Redis** or a database to support multiple workers and persistence across restarts.
- Add **rate limiting** on the `/api/start-job` endpoint to prevent abuse.
- Run behind a reverse proxy (nginx/Caddy) with proper timeout settings for long-running SSE connections.
- Build the React frontend (`npm run build`) and have FastAPI serve the static files, or deploy separately.
- Consider **worker queues** (Celery, ARQ) for better job management at scale.

---

## 🤝 Contributing

Contributions and feature requests are welcome! Feel free to open an [issue](https://github.com/PrantikM/docbuild/issues) or submit a pull request.

---

## 📄 License

This project is open-source. Feel free to use and build on it.

---

> Built with ❤️ by [PrantikM](https://github.com/PrantikM)
