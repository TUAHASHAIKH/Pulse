<div align="center">

# 🫀 Pulse (`pulse-agent`)

### Autonomous Multi-Agent DevOps & Code Review System

**AI-powered code review · Automated repair · Production self-healing**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![npm version](https://img.shields.io/npm/v/pulse-agent.svg?style=flat-square)](https://www.npmjs.com/package/pulse-agent)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Node 18+](https://img.shields.io/badge/node-18+-green.svg)](https://nodejs.org/)

</div>

---

Pulse is an open-source, multi-agent DevOps system that reviews your code before it merges and watches your applications after they deploy. A team of specialised AI agents — coordinated through **[LangGraph](https://github.com/langchain-ai/langgraph)** — catches security flaws, performance regressions, and code-quality issues on every pull request, attempts to fix critical problems automatically inside an isolated Docker sandbox, and streams live diagnostics to a real-time web dashboard.

---

## ✨ Features

- **🔍 AI Code Review** — Specialized Security, Performance, and Code Quality agents review every PR and git diff in parallel.
- **🔧 Automated Repair** — Critical issues are automatically patched and tested inside an isolated Docker sandbox.
- **📊 Real-Time Web Dashboard** — Beautiful Next.js UI showing live agent thinking, file recommendations, and system metrics.
- **⚡ CLI-First (`pulse-agent`)** — Install once with npm and use the `pulse` CLI command across any project on your computer with zero manual virtualenv management.

---

## 🚀 Quick Start (CLI — Recommended)

### 1. Install Globally

Install the Pulse CLI globally from npm:

```bash
npm install -g pulse-agent
```

> **Note:** Requires **Node.js 18+** and **Python 3.11+** installed on your system.

### 2. Initialize in Any Project

Navigate to any Git repository on your machine and run:

```bash
cd /path/to/your-project
pulse init
```

The interactive wizard will:
- Let you choose your LLM provider (**Anthropic**, **OpenAI**, or **Groq**) and save your API key.
- Optionally configure your **GitHub token** for remote pull request reviews.
- Create a `.pulse/config.json` configuration file in your project directory.
- Automatically add `.pulse/` to your `.gitignore`.

### 3. Start Pulse

```bash
pulse start
```

This launches both the **Python Orchestrator Backend** (`http://localhost:8000`) and the **Interactive Web Dashboard** (`http://localhost:3000`) in the background.

- On first run, Pulse automatically detects Python 3.11+ and creates a self-contained virtual environment inside `.pulse/.venv/`.
- It installs required Python packages using hash-based caching so subsequent startups take less than a second!

---

## 🛠️ CLI Reference (`pulse`)

| Command | Description |
|---|---|
| `pulse init` | Interactive setup wizard to configure API keys for the current project |
| `pulse start` | Start the Pulse backend orchestrator (`:8000`) and UI dashboard (`:3000`) |
| `pulse review` | Analyze your local staged/unstaged `git diff` using all AI agents |
| `pulse review --pr owner/repo#123` | Review a remote GitHub Pull Request |
| `pulse status` | Display a live health check table of all Pulse services and ports |
| `pulse stop` | Gracefully shut down background orchestrator and dashboard processes |

---

## 🌐 Interactive Dashboard

When Pulse is running (`pulse start`), open your browser to:
👉 **[http://localhost:3000](http://localhost:3000)**

- **Live Agent Pipeline:** Watch Security, Performance, and Quality agents analyze your code in real time via Socket.io.
- **Detailed Findings:** Filter recommendations by severity (**Critical**, **Warning**, **Info**) and inspect exact line numbers.
- **Interactive Repair Panel:** Review Docker sandbox patches and apply automated fixes directly to your files.

---

## 🏗️ Architecture & Monorepo Structure

```
GitHub PR / git diff ──→ FastAPI Orchestrator ──→ LangGraph Multi-Agent Graph
                               │                              │
                           Socket.io ◄─────────────── Agent Findings
                               │                              │
                        Web Dashboard                Repair Agent (Docker)
                       (localhost:3000)             (sandbox → test → patch)
```

```
pulse/
├── packages/
│   ├── orchestrator/    # FastAPI + LangGraph backend (Python 3.11+)
│   ├── dashboard/       # Next.js real-time UI (React 19 + standalone build)
│   └── cli/             # npm CLI package (Commander.js + process lifecycle)
├── docs/
│   └── agent-prompts/   # Versioned system prompts for each agent
├── infra/
│   └── k8s/             # Kubernetes manifests
└── package.json         # Monorepo root
```

---

## 💻 Developer & Contributor Setup

If you want to contribute to the Pulse codebase or run from source:

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/pulse.git
cd pulse

# 2. Install Node dependencies
npm install

# 3. Build dashboard and CLI
npm run build:dashboard
npm run build:cli

# 4. Link CLI globally for development
cd packages/cli
npm link

# 5. Start development servers
npm run dev
```

---

## 🗺️ Roadmap & Progress

| Phase | Status | Description |
|---|---|---|
| 1. Orchestrator Skeleton | ✅ | FastAPI + webhook receiver + Socket.io |
| 2. Security Agent (E2E) | ✅ | First agent: diff in → findings out → PR comment |
| 3. Multi-Agent Wiring | ✅ | LangGraph parallel fan-out to Security, Performance, and Quality agents |
| 4. Repair Agent + Sandbox | ✅ | Docker-based automated fix attempts and code patch generation |
| 5. Dashboard | ✅ | Next.js real-time UI with live neural graph and findings feed |
| 6. CLI Packaging | ✅ | `pulse-agent` npm CLI (`pulse start`, `pulse review`, etc.) |
| 7. Sentinel + Self-Healing | ⬜ | Kubernetes cluster monitoring (stretch goal) |

---

## 🤝 Contributing

Contributions are welcome! Please read the [contributing guidelines](CONTRIBUTING.md) before submitting a PR.

## 📄 License

MIT — see [LICENSE](LICENSE) for details.