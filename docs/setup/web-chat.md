# Web Chat Setup

A browser chat front end over the same `NetBoxDeepAgent` the CLI uses. Nothing about the
agent changes: same tools, same system prompt, same middleware. The web layer adds streaming,
tool-activity display, cancellation, per-conversation memory, and token/context accounting.

Design and rationale: `PRPs/netbox-web-chat.md` and
`docs/development/2026-09-28_web-chat.md`.

## Ports (defined once each)

| Service        | Port  | Where it is set                                  |
|----------------|-------|--------------------------------------------------|
| NetBox         | 8000  | docker (unchanged)                               |
| llama-server   | 58123 | `scripts/serve_qwen4exp.sh`                      |
| Web backend    | 8010  | `WEB_PORT` in `.env` (read by `src/web/config.py`) |
| Web frontend   | 3010  | `frontend/nuxt.config.ts` (`devServer.port`) / `PORT` |

8001/8002 belong to the `claude-agentic-sdk` chatbox; 11434 is Ollama.

## Install

```bash
cd /home/ola/dev/netboxdev/ollamaDeepAgents
./venv/bin/pip install -e ".[web,dev]"
cd frontend && npm install && cd ..
cp frontend/.env.example frontend/.env   # defaults already point at :8010
```

`.env` must have `LLM_BACKEND=llamacpp`, `LLAMACPP_MODEL=qwen3.8-flash-next-UD-Q4_K_XL`,
`LLAMACPP_BASE_URL=http://localhost:58123/v1`, `NETBOX_URL`, `NETBOX_TOKEN`, `MCP_SERVER_PATH`.
The `WEB_*` variables are optional; defaults are in `.env.example`.

## Run (three terminals)

```bash
# 1. model server (skip if already up: curl -s 127.0.0.1:58123/health)
scripts/serve_qwen4exp.sh

# 2. backend — check first that no stale token is exported in the shell:
env | grep -i netbox_token && echo "WARNING: shell NETBOX_TOKEN overrides .env"
./venv/bin/python -m src.web
#    -> http://127.0.0.1:8010/health  /status  /docs

# 3. frontend
cd frontend && npm run dev
#    -> http://localhost:3010
```

The backend's own process disables the blocking start-up model probe
(`LLAMACPP_VALIDATE_ON_INIT=false`); the CLI keeps it.

## Protocol check without a browser

```bash
./venv/bin/python scripts/ws_smoke.py "What sites do I have?" --usage
./venv/bin/python scripts/ws_smoke.py "Show devices at site DM-Akron" --follow-up "How many are active?"
./venv/bin/python scripts/ws_smoke.py "Describe every device at every site" --cancel-after 20
```

`ws_smoke.py` speaks the exact WebSocket protocol the browser uses and prints every chunk type
(text deltas, tool calls, per-model-call usage, done/error summary, and the server ledger).

## Endpoints

| Route | Purpose |
|---|---|
| `GET /health` | `healthy` / `degraded` (llama-server unreachable) / `unhealthy` (agent not built) |
| `GET /status` | model alias, `n_ctx`, compaction trigger, slot busy, prompt-cache tokens, turn running, queue depth |
| `GET /models` | the one loaded model (informational; no switching) |
| `GET /conversations/{id}/messages` | user/assistant transcript from the checkpointer (404 if unknown) |
| `GET /conversations/{id}/usage` | cumulative token ledger for the thread |
| `DELETE /conversations/{id}` | forget the thread on the server: checkpoints and ledger (409 while a turn runs on it) |
| `GET /conversations/{id}/traces` | the thread's LangSmith root runs (oldest first) with trace URLs; `[]` when tracing is off. Served from LangSmith, so it works for threads the backend no longer remembers; the UI uses it to backfill "trace" links on older turns |
| `WS /ws/chat` | chat stream; see `src/web/models.py` for `ChunkType` and `ClientMessage` |

## What the numbers mean

- **ctx / context gauge** — `input_tokens` of the turn's *last* model call, as reported by
  llama-server. This is the resident context. It is not an estimate; the in-process
  `count_tokens_approximately` undercounts ~19x and is not used anywhere.
- **cached** — `prompt_tokens_details.cached_tokens`: prompt tokens served from llama-server's
  prefix cache. High on a continued thread, ~0 after switching conversations.
- **written** — `completion_tokens`, which *includes reasoning tokens*. "1 call, 8192 written,
  0 chars" is the output-budget failure; the UI shows it as an error, not an empty bubble.
- **prefill / decode t/s** — llama.cpp `timings.prompt_per_second` / `predicted_per_second`,
  preserved by the `LlamaCppChatOpenAI` subclass. Shown as `n/a` when absent, never `0`.
- **compaction** — a >20% drop in `input_tokens` between consecutive calls; the transcript gets a
  divider. The trigger is 0.85 x `n_ctx` (~111k on the current server).
- **trace link** — every turn footer ends with "trace ↗" when LangSmith tracing is on
  (`LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY`). The backend mints the LangGraph root
  `run_id` for each turn and builds
  `https://smith.langchain.com/o/<org>/projects/p/<project>/r/<run_id>?trace_id=<run_id>`;
  the org/project ids are looked up once at startup from `LANGCHAIN_PROJECT`. The same
  `run_id` and `trace_url` are in the `done`/`error`/`cancelled` chunk metadata and the ledger.

## Known limits

- **One turn at a time.** The llama-server has one slot and the MCP client is a stdio
  subprocess, so the backend serialises turns. A second tab sees `queued (n)`.
- **Memory survives backend restarts** (since 2026-10-05). LangGraph checkpoints live in SQLite at
  `WEB_CHECKPOINT_DB` (default `data/web_checkpoints.sqlite`, project-root relative). Conversations
  created before that date exist only in the browser and show a "no memory of this conversation"
  banner. Back up the database together with `conversation_history/` and `large_tool_results/`,
  which hold the summarizer's offloaded artifacts for the same threads. The CLI and the eval
  harness still use per-process memory on purpose.
- **Cancel rolls the thread back.** Stop removes the cancelled question and any partial tool loop
  from the server thread, so later answers are not influenced by it. The browser keeps the
  cancelled bubble for the record.
- **Switching conversations is slow on the first turn.** Different history = different prefix =
  cold prefill (measured 81.8 s for 8.7k tokens).
- **No auth.** Bind stays on `127.0.0.1`. Single-operator tool.
- `conversation_history/` and `large_tool_results/` grow with every conversation (DeepAgents
  middleware artefacts, gitignored).

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `/health` says `degraded` | llama-server down or on another port; check `LLAMACPP_BASE_URL` |
| Tool calls return `TOOL_API_ERROR ... 403` | a `NETBOX_TOKEN` exported in the shell overrides `.env` and is inherited by the MCP subprocess |
| Ledger shows zeros | `stream_usage` not set on the model; see `create_llamacpp_model()` |
| `No streaming chunk received for 120.0s` error after a big tool result | langchain-openai's async streaming watchdog; llama-server is silent while it prefills a large prompt. Keep `LLAMACPP_STREAM_CHUNK_TIMEOUT_S=0` (default) or raise it well above your longest prefill |
| Empty bubble | should not happen; if it does, check backend log for `finish_reason=length` and file it |
| `Opening checkpoint store` then startup fails | the `WEB_CHECKPOINT_DB` path is unwritable or locked by another process; fix the path. The server never falls back to in-memory |
| Backend port in use | 8000 is NetBox, 8001/8002 the claude app; change `WEB_PORT` and `NUXT_PUBLIC_*` together |
