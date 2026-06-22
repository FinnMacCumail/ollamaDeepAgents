# Ollama Cloud Setup

Run the agent against frontier-scale models hosted by Ollama. The current default is `deepseek-v4-flash:cloud` (284B params, 13B active, 1M-token context) — the model-matrix eval found it matches the larger `deepseek-v4-pro:cloud` (1.6T/49B) on answer quality while running ~36% faster. The local Ollama daemon transparently proxies `:cloud`-suffixed model names to `ollama.com`, so the rest of the stack (`langchain-ollama`, DeepAgents, MCP) is unchanged.

**Trade-off:** Queries and tool results leave the machine. Use the [llama.cpp setup](llamacpp.md) instead for privacy-critical environments.

## Prerequisites

1. **Ollama daemon running locally.** Confirm with `curl http://localhost:11434/api/tags`.
2. **Ollama Cloud Pro subscription.** Free tier does not unlock `:cloud` frontier models. Subscribe at [ollama.com/upgrade](https://ollama.com/upgrade) ($20/mo or $200/yr). Note: the Pro tier has rolling session + weekly usage limits — a full 10-model eval-matrix sweep can exhaust the session window; see `docs/development/2026-06-14_deepagents-0.6-upgrade.md` and the eval harness notes.
3. **Signed in.** Run `ollama signin` (one-time browser auth).

## Smoke test

```bash
ollama run deepseek-v4-flash:cloud "say hello"
```

Expected: a response. If you get `403 Forbidden: this model requires a subscription`, the subscription hasn't activated yet — wait a minute and retry, or check `ollama.com/settings`. A `404 model ... not found` means that specific `:cloud` model isn't in your subscription's catalog.

## Configuration

Edit `.env`:

```bash
LLM_BACKEND=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=deepseek-v4-flash:cloud
OLLAMA_TEMPERATURE=0.0
```

Then start the agent:

```bash
./venv/bin/python -m src.main
```

No code changes are needed — `src/agents/ollama_config.py` detects the `:cloud` suffix and:

- Skips the warm-up `llm.invoke("test")` probe (avoids a billable round-trip on every restart).
- Disables the local-model fallback (`mixtral:8x7b`) — surfaces real cloud errors (auth, quota, network) instead of silently demoting.
- Uses a 32K context window by default. Raise `num_ctx` in `ollama_config.py` if you need more (model supports 1M, latency scales with context).

## Other available cloud models

Per Ollama's catalog (subject to change — check [ollama.com/search?c=cloud](https://ollama.com/search?c=cloud)):

- `deepseek-v4-flash:cloud` — **default**, 284B/13B MoE, matches pro quality at ~36% lower latency
- `deepseek-v4-pro:cloud` — 1.6T MoE, strong tool calling, 1M context
- `glm-5:cloud` — 744B/40B MoE, fastest in the eval matrix (LangChain's own DeepAgents reference model)
- `kimi-k2.6:cloud`, `minimax-m3:cloud`, `nemotron-3-ultra:cloud` — other frontier options scored in the matrix
- `gpt-oss:120b-cloud` — open-weights baseline

These were all benchmarked in the 10-model cloud sweep — see `docs/development/2026-06-14_deepagents-0.6-upgrade.md` and the `netbox-benchmark-v2` results. The Pydantic validator at `src/utils/config.py` gates `OLLAMA_MODEL` against an `allowed_prefixes` list (currently `gpt-oss:`, `qwen2.5:`, `qwen2:`, `qwen3-coder:`, `deepseek-r1:`, `deepseek-r:`, `deepseek-v3.1:`, `deepseek-v4-pro:`, `deepseek-v4-flash:`, `llama3.1:`, `llama3.2:`, `llama3:`, `mixtral:`). Add new prefixes there, or set `DEBUG=true` to bypass validation. Note: the **eval harness** (`tests/eval/run_matrix.py`) bypasses this validator entirely via `load_netbox_config()`, so it can test arbitrary models without editing the allowlist.

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
