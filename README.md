# Hybrid AI Coder

Hybrid AI Coder is a local-first coding orchestrator that combines:

- a local model (`qwen3-coder` via Ollama) for most implementation work
- a cloud model (`gpt-5.3-codex`) for escalation, difficult tasks, and high-risk scenarios

The goal is to reduce cloud token usage without losing quality for complex engineering work.

## Why use Hybrid AI Coder

### 1. Lower cloud cost
- Most tasks are executed locally by default.
- Cloud model is invoked only when needed (complex/risky tasks or repeated local failures).

### 2. Better control and safety
- Local-first routing avoids sending full repository context by default.
- Context minimization keeps prompts compact and focused.
- Approval/review flows allow human control before applying risky changes.

### 3. Practical productivity
- Web UI with codex-style layout.
- Task history, status tracking, and review panel with git-style diffs.
- File upload support with model capability-aware image handling.

### 4. Multi-model ready architecture
- Provider config supports local and cloud providers.
- You can extend routing and adapters for OpenAI, Azure OpenAI, Anthropic, Copilot-style setups, etc.

## Core architecture

- **Router**: decides local vs cloud execution
- **Planner / Orchestrator**: decomposes and runs subtasks
- **Executors**:
  - local (`OllamaExecutor`)
  - cloud (`GPTExecutor` + provider adapters)
- **Task Store**: persistent task/event history (SQLite)
- **UI**: FastAPI + HTMX codex-like interface

## Prerequisites

- Python 3.9+
- Ollama installed and running
- Local model pulled (example: `qwen3-coder`)
- Optional: OpenAI API key for cloud escalation

## Setup

### 1. Clone
```bash
git clone https://github.com/Shrikar/hybrid-ai-coder.git
cd hybrid-ai-coder
```

### 2. Install Python dependencies
```bash
python3 -m pip install -r requirements.txt
```

If your repo does not include `requirements.txt`, install the core dependencies used by the app:
```bash
python3 -m pip install fastapi uvicorn httpx python-dotenv jinja2 sse-starlette pytest
```

### 3. Start Ollama and pull local model
```bash
ollama serve
ollama pull qwen3-coder
```

### 4. Configure cloud key (optional but recommended)
```bash
export OPENAI_API_KEY="<your_key>"
```

### 5. Configure app
Main config file:
- `config/config.json`

Key fields to verify:
- `active.local_provider` = `ollama`
- `providers.ollama.model` = `qwen3-coder`
- `active.cloud_provider` = `openai`
- `providers.openai.model` = `gpt-5.3-codex`

## Run

From `hybrid-ai-coder` directory:
```bash
uvicorn backend.api.main:app --reload --host 127.0.0.1 --port 8001
```

Open UI:
- `http://127.0.0.1:8001/ui`

## How to use

1. Enter prompt in the bottom composer.
2. Choose mode:
   - `auto` (recommended): local-first with smart escalation
   - `local`: force local model only
   - `gpt`: force cloud model
3. Upload files if needed (text and image attachments supported).
4. Submit task.
5. Click a task in Task History to view:
   - event timeline
   - LLM outputs
   - Task Details
   - Review Panel with git-style diffs

## Image attachment behavior

- Upload is always allowed.
- In `auto` mode:
  - if local model supports vision, image stays local
  - if local model does **not** support vision, task escalates to cloud automatically

## Local-first advantage in practice

Typical flow:
- Simple implementation tasks: local only
- Hard architecture/security/concurrency tasks: cloud when needed
- Failed local retries: controlled escalation to cloud

This gives a better cost/quality balance than always-cloud execution.

## Token Savings Snapshot

The app tracks savings metrics in Task Store and exposes them in UI/API.

Example snapshot (real run format):

```text
totalTasks: 154
localOnlyTasks: 105
localOnlyRate: 0.6818
avgGptCallsPerTask: 0.23
avgGptTokensPerTask: 0.0
avgGptCostPerTaskUsd: 0.0
```

What this means:
- ~68% of tasks completed without any GPT call.
- GPT usage is concentrated on a smaller subset of harder tasks.
- Cost trend can be tracked per project with `/api/v1/tasks/metrics/savings/projects`.

You can compare this against an always-cloud baseline by estimating:

```text
estimated_tokens_saved = (baseline_avg_tokens_per_task - avgGptTokensPerTask) * totalTasks
```

For example, if an always-cloud baseline is 2,000 tokens/task:

```text
estimated_tokens_saved = (2000 - 0) * 154 = 308,000 tokens
```

## Security notes

- Never commit secrets (`.env` is ignored).
- If a secret was ever committed, rotate it immediately and rewrite history.
- Keep API keys in environment variables, not source files.

## Troubleshooting

### Ollama connection failed
- Ensure Ollama is running: `ollama serve`
- Ensure base URL in config is correct (`http://localhost:11434`)

### Cloud escalation not working
- Verify `OPENAI_API_KEY` is set
- Verify selected cloud provider config in `config/config.json`

### UI clicks not updating details
- Hard refresh browser (`Cmd+Shift+R` on macOS)
- Check server logs for frontend/HTMX errors

## Development and tests

Run key tests:
```bash
python3 -m pytest -q tests/test_ui_smoke.py
python3 -m pytest -q tests/test_router.py
python3 -m pytest -q tests/test_skills_api.py
```

## Roadmap ideas

- richer project mode: ask clarifications -> plan -> execute pipeline in one chat thread
- stronger provider capability registry (vision/tools/code-interpreter flags)
- improved per-project cost dashboard and routing analytics
