<div align="center">

# 🫀 Pulse

### Autonomous Multi-Agent DevOps System

**AI-powered code review · Automated repair · Production self-healing**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Node 18+](https://img.shields.io/badge/node-18+-green.svg)](https://nodejs.org/)

</div>

---

Pulse is an open-source, multi-agent DevOps system that reviews your code before it merges and watches your applications after they deploy. A team of specialised AI agents — coordinated through [LangGraph](https://github.com/langchain-ai/langgraph) — catches security flaws, performance regressions, and code-quality issues on every pull request, attempts to fix critical problems automatically inside a Docker sandbox, and (optionally) watches Kubernetes clusters to detect and self-heal production incidents.

## ✨ Features

- **🔍 AI Code Review** — Security, performance, and code quality agents review every PR automatically
- **🔧 Automated Repair** — Critical issues are fixed inside an isolated Docker sandbox, tested, and proposed back
- **📊 Live Dashboard** — Real-time Next.js dashboard showing agent activity as it happens
- **🛡️ Kubernetes Self-Healing** — (Stretch) Sentinel watches your cluster and auto-recovers from incidents
- **⚡ CLI-First** — Run `pulse start` and everything works — no cloud account, no signup

## 🏗️ Architecture

```
GitHub PR Event ──→ FastAPI Orchestrator ──→ LangGraph Agent Graph
                         │                        │
                    Socket.io ◄────────────── Agent Findings
                         │                        │
                    Dashboard              Repair Agent (Docker)
                  (localhost:3000)          (sandbox → test → patch)
```

## 📦 Project Structure

```
pulse/
├── packages/
│   ├── orchestrator/    # FastAPI + LangGraph backend (Python)
│   ├── dashboard/       # Next.js real-time UI
│   └── cli/             # npm CLI wrapper
├── docs/
│   └── agent-prompts/   # Versioned system prompts for each agent
├── infra/
│   └── k8s/             # Kubernetes manifests (Phase 7)
└── package.json         # Monorepo root
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker Desktop (for Repair Agent sandbox)
- A GitHub account
- An LLM API key ([Anthropic](https://console.anthropic.com/) or [OpenAI](https://platform.openai.com/))

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/pulse.git
cd pulse

# 2. Set up the orchestrator
cd packages/orchestrator
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt

# 3. Configure environment
cp ../../.env.example .env
# Edit .env with your GITHUB_WEBHOOK_SECRET and LLM_API_KEY

# 4. Start the orchestrator
uvicorn app.main:app --reload --port 8000

# 5. Visit http://localhost:8000/docs to see the API
```

### Verify It's Working

```bash
# Health check
curl http://localhost:8000/health

# Expected: {"status":"ok","version":"0.1.0","uptime_seconds":...}
```

## 🔧 Configuration

Copy `.env.example` to `.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `GITHUB_WEBHOOK_SECRET` | Yes | Secret for verifying GitHub webhooks |
| `LLM_API_KEY` | Phase 2+ | Your Anthropic or OpenAI API key |
| `LLM_PROVIDER` | Phase 2+ | `anthropic` or `openai` |
| `ORCHESTRATOR_PORT` | No | Server port (default: 8000) |
| `DASHBOARD_ORIGIN` | No | Dashboard URL for CORS (default: http://localhost:3000) |

## 🗺️ Roadmap

| Phase | Status | Description |
|---|---|---|
| 1. Orchestrator Skeleton | ✅ | FastAPI + webhook receiver + Socket.io |
| 2. Security Agent (E2E) | ⬜ | First agent: diff in → findings out → PR comment |
| 3. Multi-Agent Wiring | ⬜ | LangGraph parallel fan-out to all reviewers |
| 4. Repair Agent + Sandbox | ⬜ | Docker-based automated fix attempts |
| 5. Dashboard | ✅ | Next.js real-time UI |
| 6. CLI Packaging | ⬜ | `npx pulse start` wraps everything |
| 7. Sentinel + Self-Healing | ⬜ | Kubernetes monitoring (stretch goal) |

## 🤝 Contributing

Contributions are welcome! Please read the [contributing guidelines](CONTRIBUTING.md) before submitting a PR.

## 📄 License

MIT — see [LICENSE](LICENSE) for details.