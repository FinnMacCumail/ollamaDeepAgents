# Ollama Cloud Setup

Run the agent against frontier-scale models hosted by Ollama (e.g. `deepseek-v4-pro:cloud` — 1.6T params, 49B active, 1M-token context). The local Ollama daemon transparently proxies `:cloud`-suffixed model names to `ollama.com`, so the rest of the stack (`langchain-ollama`, DeepAgents, MCP) is unchanged.

**Trade-off:** Queries and tool results leave the machine. Use the [llama.cpp setup](llamacpp.md) instead for privacy-critical environments.

## Prerequisites

1. **Ollama daemon running locally.** Confirm with `curl http://localhost:11434/api/tags`.
2. **Ollama Cloud Pro subscription.** Free tier does not unlock `deepseek-v4-pro:cloud`. Subscribe at [ollama.com/upgrade](https://ollama.com/upgrade) ($20/mo or $200/yr).
3. **Signed in.** Run `ollama signin` (one-time browser auth).

## Smoke test

```bash
ollama run deepseek-v4-pro:cloud "say hello"
```

Expected: a response. If you get `403 Forbidden: this model requires a subscription`, the subscription hasn't activated yet — wait a minute and retry, or check `ollama.com/settings`.

## Configuration

Edit `.env`:

```bash
LLM_BACKEND=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=deepseek-v4-pro:cloud
OLLAMA_TEMPERATURE=0.0
```

Then start the agent:

```bash
source venv/bin/activate
python -m src.main
```

No code changes are needed — `src/agents/ollama_config.py` detects the `:cloud` suffix and:

- Skips the warm-up `llm.invoke("test")` probe (avoids a billable round-trip on every restart).
- Disables the local-model fallback (`mixtral:8x7b`) — surfaces real cloud errors (auth, quota, network) instead of silently demoting.
- Uses a 32K context window by default. Raise `num_ctx` in `ollama_config.py` if you need more (model supports 1M, latency scales with context).

## Other available cloud models

Per Ollama's catalog (subject to change — check [ollama.com/search?c=cloud](https://ollama.com/search?c=cloud)):

- `deepseek-v4-pro:cloud` — 1.6T MoE, strong tool calling, 1M context
- `qwen3-coder:480b-cloud` — coding-specialised
- `gpt-oss:120b-cloud`, `gpt-oss:20b-cloud` — open weights baselines
- `deepseek-v3.1:671b-cloud` — older-generation reference

The Pydantic validator at `src/utils/config.py` accepts these prefixes; add new ones to `allowed_prefixes` if you experiment with others.

## Switching back to local

Edit `.env`:

```bash
LLM_BACKEND=llamacpp
# ...or:
LLM_BACKEND=ollama
OLLAMA_MODEL=qwen2.5:32b-instruct-q4_K_M    # any local-pulled model
```

No restart of the Ollama daemon required — only the agent process needs to be re-run.

## Cost & rate limits

- Pro is a flat $20/mo subscription — no per-token billing during preview.
- Usage is metered as **GPU-time** (model size × request duration), not tokens.
- "50× more usage than Free" per the [pricing page](https://ollama.com/pricing); concrete caps aren't published — monitor at `ollama.com/settings`.
- Pay-as-you-go per-token billing is announced as "coming soon" but not yet available.
- Hard rate limits aren't documented; expect some throttling under sustained agent loops.

## Troubleshooting

**`403 Forbidden: this model requires a subscription`**
Subscription not active for this account. Verify at `ollama.com/settings`, retry `ollama signin` if needed.

**`Connection error` / `Connection refused`**
Local Ollama daemon isn't running. Start it (`ollama serve`) or check the systemd / launchd service.

**Validator rejects model name (`Model must start with one of: ...`)**
The new `:cloud` model isn't in the allow-list. Add the prefix to `allowed_prefixes` in `src/utils/config.py`, or set `DEBUG=true` in `.env` to bypass.

**Slow first response**
Cold-start latency on cloud-hosted MoE models can spike the first call. Subsequent calls in a memory-enabled session benefit from prompt caching.
