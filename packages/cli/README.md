# 🫀 Pulse (`pulse-agent`)

**AI-powered code review from your terminal — security, performance, and quality agents on every PR.**

Pulse brings automated multi-agent code reviews directly to your development workflow. It combines a terminal CLI with an interactive web dashboard so you can review pull requests or local git diffs before pushing.

---

## 🚀 Quickstart

### 1. Install Globally

```bash
npm install -g pulse-agent
```

> **Note:** Requires **Node.js 18+** and **Python 3.11+** installed on your machine.

### 2. Initialize in Any Project

Navigate to any git repository on your computer and run:

```bash
cd /path/to/your-repo
pulse init
```

This interactive setup wizard will:
- Ask for your LLM provider (**Anthropic**, **OpenAI**, or **Groq**) and API key
- Optionally configure your **GitHub token** for PR reviews
- Create a `.pulse/config.json` file in your project root
- Automatically add `.pulse/` to your `.gitignore`

### 3. Start Pulse

```bash
pulse start
```

This boots both the **Python Orchestrator API** (`http://localhost:8000`) and the **Interactive Web Dashboard** (`http://localhost:3000`) in the background.

- On first start, Pulse automatically creates a Python virtual environment at `.pulse/.venv/` and installs the required dependencies.
- No manual `pip install` or `venv` management needed!

---

## 🛠️ CLI Commands

| Command | Description |
|---|---|
| `pulse init` | Interactive setup wizard to configure API keys for the current project |
| `pulse start` | Start the Pulse orchestrator (`:8000`) and dashboard (`:3000`) |
| `pulse review` | Trigger a review on your local staged/unstaged `git diff` |
| `pulse review --pr owner/repo#123` | Review a remote GitHub Pull Request |
| `pulse status` | Display a health check table of all Pulse components |
| `pulse stop` | Gracefully shut down running Pulse background processes |

---

## 🌐 Interactive Dashboard

When Pulse is running (`pulse start`), open your browser to:
👉 **[http://localhost:3000](http://localhost:3000)**

You'll see:
- **Live Agent Pipeline:** Watch Security, Performance, and Quality agents analyze your code in real time.
- **Detailed Findings:** Filter reviews by severity (**Critical**, **Warning**, **Info**) and inspect exact file/line recommendations.
- **Left Navigation Panel:** Seamlessly switch between code reviews, agent status, and settings.

---

## 🏗️ How It Works (Architecture)

```
Your Project Repo/
  ├── .pulse/
  │     ├── config.json       # Your API keys & preferences
  │     ├── .venv/            # Auto-managed Python environment
  │     └── .pid.json         # Background process tracking
  └── ...your codebase
```

1. **Self-Contained Bundling:** The CLI package bundles the Python backend and Next.js frontend directly inside the npm package.
2. **Zero-Configuration Venv:** When `pulse start` runs, it detects Python 3.11+, sets up a venv inside `.pulse/`, and installs requirements using hash-based caching to skip redundant installs.
3. **Multi-Agent Orchestration:** Reviews are powered by LangGraph, routing code changes through specialized security, performance, and quality analyzers.

---

## 📦 Publishing to npm

To publish or update this package on npm:

```bash
cd packages/cli
npm publish
```

The `prepublishOnly` script automatically runs `npm run prepare-bundle` to bundle the latest orchestrator and pre-built dashboard into the package before uploading.
