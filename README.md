# Hybrid AI Coder

Local-first hybrid AI coding orchestrator.

- Default executor: local `qwen3-coder` via Ollama
- Escalation executor: `gpt-5.3-codex`
- Objective: minimize cloud token usage by routing GPT only for high-risk/complex or failed local runs
