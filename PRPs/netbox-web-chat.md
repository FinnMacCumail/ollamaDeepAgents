name: "NetBox Web Chat on the local Qwen3.8-Flash-Next agent (FastAPI + Nuxt)"
description: |
  Add a browser chat front end and a streaming WebSocket back end to the existing NetBox
  DeepAgents query system, which today runs only as a Rich CLI (`python -m src.main`) against a
  locally served Qwen3.8-Flash-Next (176B MoE) on llama.cpp. Modelled on the Claude Agent SDK
  chatbox PRP (`claude-agentic-sdk/PRPs/netbox-chatbox.md`), with the agent, memory and
  inference layers swapped for what this repo already has.

## Purpose
Give the operator a browser chat window over the *existing* `NetBoxDeepAgent` without changing
how the agent reasons, which tools it has, or how the eval harness measures it. Token-level
streaming, tool-activity display, cancellation and per-conversation memory are the deliverable.
Inference stays on this machine.

## Core Principles
1. **Context is King**: every file, flag and measured number the implementer needs is in here or linked.
2. **Validation Loops**: ruff/mypy, pytest with a fake agent, a WebSocket smoke client, then a real end-to-end run.
3. **Information Dense**: identifiers below are the real ones from `src/`, `scripts/` and the claude-agentic-sdk app.
4. **Progressive Success**: back end + smoke client first (Tasks 1-8), then front end (9-14), then docs.
5. **Global rules**: follow CLAUDE.md and AGENTS.md (read-only NetBox, `./venv/bin/python`, no hardcoded model names, decision note in `docs/development/`).

---

## Goal
A user opens `http://localhost:3010`, types a NetBox question, and watches the answer stream in
token by token while a side panel shows each NetBox tool call (name, key args, ok/error). They can
cancel a turn, start a new conversation, switch between conversations, and see whether the model
server is busy. Follow-up questions use the same LangGraph thread, so the agent remembers earlier
turns. The CLI, `tests/eval/` and `NetBoxDeepAgent.query()` continue to work unchanged.

## Why
- **Latency is the UX problem.** Measured per-turn wall time on the local model is 35 s to 486 s
  (`docs/traces/2026-09-24_netbox-session_*.md`), decode ~12-15 tok/s. The CLI prints nothing until
  the whole answer exists (`src/main.py:134-147`). Streaming plus tool activity is a functional
  requirement here, not polish.
- **Conversation hygiene is a correctness lever.** The same 11 questions in two orders scored
  0.750 vs 0.950 (commit `48fadb6`): a later turn answered from a wrong population inherited from an
  earlier turn. A visible "new conversation" control and a per-turn tool-call display let the user
  see and break that contamination.
- **Pre-declared want.** `TODO.md:58-63` and `CHANGELOG.md:56-59` list a web interface as planned.
- **Privacy mandate holds.** The `claude-agentic-sdk` chatbox sends data to Anthropic; this one
  keeps it on `127.0.0.1:58123`. The anonymisation retrospective concluded the lever for data
  residency is *where inference runs* - which is exactly this project's llama.cpp path.

## What
### User-visible behaviour
- Chat page with history, streaming assistant bubble (markdown + tables), user bubbles.
- Tool activity: one line per tool call as it happens (`netbox_get_objects dcim.site {...}`),
  turning into ok / `TOOL_VALIDATION_ERROR` / `TOOL_API_ERROR` when the result arrives.
- Cancel button during a turn; "New conversation" button; conversation sidebar (localStorage).
- Status bar: WebSocket state, model alias, "model busy / queued (n)" while another turn runs.
- Turn footer: elapsed seconds, tool-call count, model calls, tokens in / out, prefill and decode
  tok/s, and a warning when the model hit its output budget.
- **Context gauge** per conversation: resident context of the last model call vs the server window
  (`n_ctx` 131072) with a marker at the 0.85 compaction trigger; turns colour amber above 50% and
  red above 85%. A "context compacted" divider appears in the transcript when the middleware
  summarises.
- **Token ledger** per conversation: cumulative prompt tokens read (and how many were served from the
  prompt cache), completion tokens written (reasoning included), model calls, wall time; per-turn
  rows expandable to per-model-call rows.

### Technical requirements
- FastAPI app in `src/web/` reusing `create_netbox_agent()`; one agent per process, created in lifespan.
- WebSocket `/ws/chat` with a JSON chunk protocol compatible in shape with the claude-agentic-sdk one
  (`{type, content, completed, metadata}`) so its composables port with minimal edits.
- New `NetBoxDeepAgent.stream_events()` using `stream_mode=["messages", "updates"]`; `query()` untouched.
- Turns serialised through one `asyncio.Lock` (single llama-server slot, stdio MCP); queue position reported.
- `thread_id` == client `conversation_id`; history reload from the checkpointer via `aget_state`.
- Nuxt 3 front end copied/adapted from `/home/ola/dev/netboxdev/claude-agentic-sdk/frontend/`.
- Ports fixed in ONE place each: back end **8010**, front end **3010** (8000 = NetBox, 8001/8002 = claude app, 58123 = llama-server, 11434 = Ollama).

### Success Criteria
- [ ] Text streams token-by-token to the browser; first token appears before the turn ends.
- [ ] Every tool call in a turn appears in the UI with its name, and its result status (ok / validation error / API error).
- [ ] Follow-up question in the same conversation is answered using earlier turns (verify with "and how many of those are active?" after a device listing).
- [ ] "New conversation" yields a fresh `thread_id`; the agent no longer knows the earlier turns.
- [ ] Cancel stops the stream within 2 s and llama-server shows the slot released (`/slots` `is_processing: false`).
- [ ] A second browser tab sending during a turn gets a `queued` chunk, then runs after the first turn finishes; no interleaved output.
- [ ] A `finish_reason == "length"` turn with no visible content surfaces as an `error` chunk, not a silent empty bubble.
- [ ] Every model call in a turn produces a `usage` chunk with `input_tokens`, `output_tokens`, `cache_read`; the turn footer shows tokens in/out and the ledger totals match the sum of the `usage` chunks.
- [ ] The context gauge equals the `input_tokens` of the turn's last model call and matches the `n_tokens` on the slot-release line in the llama-server log within 1% (the ground truth `run_session.py:40-50` identifies).
- [ ] Prefill and decode tok/s shown per turn come from llama-server `timings`, not from wall-clock estimates.
- [ ] A conversation driven past the 0.85 compaction trigger shows a "context compacted" divider and the gauge drops.
- [ ] `ruff`, `mypy`, `pytest tests/` pass; `npm run build` passes; existing `tests/test_netbox_integration.py` unchanged and green.
- [ ] `python -m tests.eval.run_session` (unchanged path) still runs; no edits to `NETBOX_SYSTEM_PROMPT`, middleware, skills or `query()`.

## All Needed Context

### Reconciliation with current reality (READ FIRST)
- `LLM_BACKEND=llamacpp`, `LLAMACPP_MODEL=qwen3.8-flash-next-UD-Q4_K_XL`, `LLAMACPP_BASE_URL=http://localhost:58123/v1` are the live `.env` values. `docs/setup/llamacpp.md` and `.env.example` still describe `Qwen_Qwen3-14B-Q5_K_M.gguf` - stale, do not copy from them.
- The server is launched by `scripts/serve_qwen4exp.sh` with **no `--parallel`**: exactly one slot. `/slots` on port 58123 returns a one-element list with `is_processing`, `n_ctx`, `n_prompt_tokens_cache`. `/health` returns `{"status":"ok"}`. `/metrics` is 501 (not enabled).
- `NetBoxDeepAgent` already has multi-turn memory: `InMemorySaver` + rolling `thread_id`, and `query(user_query, thread_id=None)` accepts an override (`src/agents/netbox_agent.py:272-275, 429-449`). Nothing to invent there.
- `query()` streams with `stream_mode="values"` and yields only final AI messages that have content and no tool calls (`netbox_agent.py:453-471`). Tool calls and tool results are filtered out. That filter is also where the "silent empty reply" failure hides (see gotchas).
- `create_llamacpp_model(validate=True)` calls the **synchronous** `llm.invoke("test")` inside the async `initialize()` (`src/agents/llamacpp_config.py:135-142`). On a cold server that blocks the event loop for up to a minute or more.
- `fastapi` is **not installed** in `./venv`; `uvicorn 0.40.0`, `starlette 0.52.1`, `websockets 15.0.1`, `sse-starlette 3.2.0`, `httpx 0.28.1` already are (transitive). Python in `./venv` is 3.12.
- Installed: `deepagents 0.7.5`, `langchain 1.3.14`, `langchain-core 1.5.3`, `langchain-openai 1.2.1`, `langgraph 1.2.5`, `langchain-mcp-adapters 0.2.1`, `pydantic 2.13.3`, `pytest 9.0.2`, `pytest-asyncio 1.3.0` (`asyncio_mode = "auto"`), `ruff 0.15.0`, `mypy 1.19.1`. Node `v22.22.2`, npm `10.9.7`.
- `langchain-openai 1.2.1` `ChatOpenAI` **drops `reasoning_content`** (module docstring, `chat_models/base.py:1-12, 580-587`). Thinking text is not available to the UI without a provider subclass. Out of scope; noted under Future.
- The claude-agentic-sdk front end on `master` is **Nuxt 3.14** (`frontend/package.json`), not the 4.x its PRP proposed. Mirror the working code, not the old PRP.
- DeepAgents' `SummarizationMiddleware` writes `conversation_history/{thread}.md` and `large_tool_results/` under `PROJECT_ROOT` (both gitignored). Every web conversation will write there too; single process, so no conflict, but it is disk growth to know about.
- **Token accounting, verified live on 2026-09-28 against `127.0.0.1:58123`:** a streamed `/v1/chat/completions` with `"stream_options":{"include_usage":true}` ends with a `choices: []` chunk carrying `usage: {prompt_tokens, completion_tokens, total_tokens, prompt_tokens_details: {cached_tokens}}` **and** a llama.cpp-specific `timings: {cache_n, prompt_n, prompt_ms, prompt_per_second, predicted_n, predicted_ms, predicted_per_second}` (server build `b11053`; `tools/server/server-task.cpp:502-517`).
- `langchain-openai 1.2.1` turns that into `AIMessageChunk.usage_metadata` = `{input_tokens, output_tokens, total_tokens, input_token_details: {cache_read}}` (`chat_models/base.py:1329-1344, 3996-4026`), **but only when `stream_usage=True`**. It is auto-enabled solely for the default OpenAI base URL (`base.py:1144-1163`); `create_llamacpp_model()` sets `base_url`, so today it is **off**. `timings` is dropped by the base class; a 12-line subclass overriding `_convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info)` (`base.py:1321`) can stash it into `response_metadata`.
- `prompt_tokens` of each model call **is** the resident context for that call. This is the number `run_session.py:40-50` says `count_tokens_approximately` undercounts ~19x (454 vs 8,751); the server figure is the ground truth and it now arrives for free on every call.
- Measured decay to plan the gauge around: decode 14.8 -> 12.6 tok/s from 9k to 46k context, 5.11 -> 1.45 tok/s between ~9k and ~76k, and the compaction trigger is `("fraction", 0.85)` of `LLAMACPP_N_CTX` = ~111k, never yet exercised (commits `c5f534b`, `48fadb6`).

### Documentation & References
```yaml
# MUST READ - codebase
- file: /home/ola/dev/netboxdev/claude-agentic-sdk/PRPs/netbox-chatbox.md
  why: The PRP this one is modelled on; same section shape, task granularity and validation levels.

- file: /home/ola/dev/netboxdev/claude-agentic-sdk/backend/api.py
  why: Proven FastAPI + WebSocket loop to mirror (lifespan L42-70, CORS L83-89, /health L92-104, /ws/chat L143-315).
  critical: Client->server JSON is {"message": str} or {"type": "reset"|"model_change"}; server->client is StreamChunk.model_dump().

- file: /home/ola/dev/netboxdev/claude-agentic-sdk/backend/models.py
  why: StreamChunk {type, content, completed, metadata} - keep this shape so the frontend composable ports.

- file: /home/ola/dev/netboxdev/claude-agentic-sdk/frontend/composables/useChatSocket.ts
  why: Reconnect (MAX_RECONNECT_ATTEMPTS=5, 2000 ms), chunk accumulation (handleStreamChunk L100-194), lifecycle. Port and extend.

- file: /home/ola/dev/netboxdev/claude-agentic-sdk/frontend/composables/useConversations.ts
  why: Module-level singleton refs + localStorage key 'netbox-conversations'. Reuse as-is, add server thread mapping.

- file: /home/ola/dev/netboxdev/claude-agentic-sdk/frontend/utils/formatters.ts
  why: marked + custom table/code renderer + DOMPurify allowlist. Copy verbatim.

- file: /home/ola/dev/netboxdev/claude-agentic-sdk/frontend/nuxt.config.ts
  why: nitro.experimental.websocket, runtimeConfig.public.wsUrl/apiUrl, tailwind module, imports.dirs. Copy, change ports.

- file: /home/ola/dev/netboxdev/claude-agentic-sdk/netbox_cli.py
  why: websockets-based CLI that speaks the same protocol as the GUI. Adapt into scripts/ws_smoke.py (Task 8).

- file: /home/ola/dev/netboxdev/claude-agentic-sdk/TROUBLESHOOTING.md
  why: Env-var inheritance into the MCP stdio subprocess (stale NETBOX_TOKEN in shell overrides .env); port 8000 collides with NetBox.

- file: src/agents/netbox_agent.py
  why: NetBoxDeepAgent (L232), initialize() L303, query() L429, new_conversation() L520, cleanup() L556, create_netbox_agent() L570.
  critical: Do NOT change query(), NETBOX_SYSTEM_PROMPT, middleware order or skills loading - eval comparability.

- file: src/agents/llamacpp_config.py
  why: n_ctx/max_tokens/reasoning_effort rationale L40-112; validate=True blocking invoke L135-142; get_llamacpp_models() L151.

- file: src/main.py
  why: L229-252 - load_dotenv() BEFORE reading LLM_BACKEND, and llamacpp branch uses load_netbox_config() not load_config(). The web entrypoint must repeat this exactly.

- file: src/tools/netbox_tools.py
  why: TOOL_VALIDATION_ERROR: / TOOL_API_ERROR: prefixes on ToolMessage content (wrapper L151-240) - classify tool results by these.

- file: tests/test_netbox_integration.py
  why: Test style - patch create_netbox_mcp_client / create_ollama_model / create_deep_agent; class-per-concern.

- file: tests/eval/run_session.py
  why: Multi-turn session pattern; per-turn state via agent.agent.aget_state(cfg) (used for history reload here too).

- file: scripts/serve_qwen4exp.sh
  why: The exact server flags and the measured numbers behind them. No --parallel.

- file: AGENTS.md
  why: Sections 2 (filter constraint), 5 (config entry points, read-only token), 7 (conventions), 8 (testing).

# MUST READ - library docs
- url: https://langchain-ai.github.io/langgraph/how-tos/streaming/
  section: "Stream multiple modes" and "messages" mode
  critical: stream_mode=["messages","updates"] yields (mode, payload) tuples; "messages" payload is (AIMessageChunk, metadata); "updates" payload is {node_name: state_delta}. Node names in this graph are "model" and "tools" (langchain/agents/factory.py:1502-1506) plus "<Middleware>.before_model/after_model".

- url: https://fastapi.tiangolo.com/advanced/websockets/
  section: WebSocketDisconnect handling; testing with TestClient.websocket_connect

- url: https://fastapi.tiangolo.com/advanced/events/
  section: lifespan - build the agent once, clean up on shutdown

- url: https://www.uvicorn.org/settings/
  section: --ws-ping-interval / --ws-ping-timeout (defaults 20 s / 20 s). Turns last minutes; keep pings on.

- url: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
  section: GET /health, GET /slots, OpenAI-compatible /v1/chat/completions streaming, --reasoning-format, --reasoning-budget
  critical: Closing the HTTP stream aborts generation server-side - this is how cancel frees the single slot.

- url: https://nuxt.com/docs/getting-started/installation
  why: Nuxt 3 project layout (pages/, components/, composables/ auto-import)

- url: https://marked.js.org/ and https://github.com/cure53/DOMPurify
  why: Already used by the claude-agentic-sdk formatters; assistant output is model-generated HTML-able markdown - sanitise.
```

### Current Codebase tree (relevant parts)
```bash
ollamaDeepAgents/
├── AGENTS.md  CLAUDE.md  README.md  TODO.md  CHANGELOG.md  pyproject.toml  .env  .env.example
├── PRPs/
│   ├── templates/prp_base.md
│   ├── initials/netbox-web-chat.md          # this feature's brief
│   ├── netbox-deepagents-ollama.md  netbox-graphql-read-tool.md  netbox-graphql-routing-and-evaluation.md
├── scripts/
│   ├── serve_qwen4exp.sh                     # llama-server launcher, port 58123, single slot
│   └── seed_benchmark_v5/ ...
├── src/
│   ├── main.py                               # Rich CLI entry point
│   ├── agents/  netbox_agent.py  llamacpp_config.py  ollama_config.py
│   ├── middleware/  filter_recovery.py  metrics.py
│   ├── tools/  netbox_tools.py  netbox_graphql.py
│   ├── skills/  netbox-mcp-filters/  netbox-graphql/
│   └── utils/  config.py  logging.py
├── tests/
│   ├── conftest.py  test_filters.py  test_netbox_integration.py  test_ollama_models.py  test_netbox_graphql.py
│   ├── eval/  run_matrix*.py  run_session.py  dataset*.py  evaluators.py
│   └── manual/  spike/  data/
├── docs/  development/  setup/  guides/  reference/  traces/  posts/
├── conversation_history/  large_tool_results/   # agent-written, gitignored
└── venv/                                     # python 3.12; use ./venv/bin/python
```

### Desired Codebase tree (files to add / modify)
```bash
ollamaDeepAgents/
├── pyproject.toml                            # MODIFY: add fastapi, uvicorn[standard], websockets; [project.optional-dependencies] web
├── .env.example                              # MODIFY: WEB_* vars + the undocumented LLAMACPP_* vars
├── src/
│   ├── agents/
│   │   ├── netbox_agent.py                   # MODIFY: add stream_events() + get_history(); query() untouched
│   │   └── llamacpp_config.py                # MODIFY: LLAMACPP_VALIDATE_ON_INIT gate; stream_usage=True; LlamaCppChatOpenAI keeps llama.cpp `timings`
│   └── web/                                  # NEW package
│       ├── __init__.py
│       ├── __main__.py                       # python -m src.web  -> uvicorn.run(app, host, port)
│       ├── config.py                         # WebConfig: host/port/CORS/queue limits, load_dotenv() FIRST
│       ├── models.py                         # Pydantic: ClientMessage, StreamChunk, HealthResponse, StatusResponse, HistoryMessage
│       ├── events.py                         # StreamEvent dataclass + translate LangGraph stream -> StreamChunk
│       ├── session.py                        # TurnRunner: asyncio.Lock, queue position, cancel, per-conversation state
│       ├── llama_status.py                   # httpx GET /health and /slots on LLAMACPP_BASE_URL (strip /v1)
│       └── api.py                            # FastAPI app: lifespan, /health, /status, /models, /conversations/{id}/messages, /ws/chat
├── scripts/
│   └── ws_smoke.py                           # NEW: CLI WebSocket client (adapted from claude-agentic-sdk/netbox_cli.py)
├── frontend/                                 # NEW Nuxt 3 app (copied from claude-agentic-sdk/frontend, then edited)
│   ├── package.json  nuxt.config.ts  tsconfig.json  .env.example  README.md
│   ├── app.vue  pages/index.vue
│   ├── assets/css/main.css
│   ├── types/chat.ts                         # extended chunk types
│   ├── utils/formatters.ts  utils/storage.ts  utils/debug.ts
│   ├── composables/useChatSocket.ts  useConversations.ts  useServerStatus.ts   # useModelSelection.ts NOT copied
│   └── components/  ChatMessage.vue  ChatInput.vue  ChatHistory.vue  ConversationSidebar.vue
│                    ConversationItem.vue  ConnectionStatus.vue  LoadingSpinner.vue
│                    ToolActivity.vue  TurnFooter.vue  ContextGauge.vue  TokenLedger.vue  CompactionDivider.vue  (all NEW)
├── tests/
│   ├── test_llamacpp_config.py               # NEW: stream_usage on; timings preserved by the ChatOpenAI subclass
│   ├── test_web_events.py                    # NEW: LangGraph stream -> chunks (text, tool_use, tool_result, usage, compaction, done, length error)
│   ├── test_web_session.py                   # NEW: lock serialisation, queue position, cancel
│   └── test_web_api.py                       # NEW: /health, /status (llama mocked), WS protocol with FakeAgent
└── docs/
    ├── development/2026-09-28_web-chat.md    # NEW decision note + README.md index line
    └── setup/web-chat.md                     # NEW: run book (3 terminals), ports, env
```

### Known Gotchas of our codebase & Library Quirks
```python
# CRITICAL (src/main.py:229-252): load .env BEFORE reading LLM_BACKEND, and on llamacpp use
# load_netbox_config(), never load_config() - OllamaConfig's prefix allow-list rejects a GGUF alias.
from dotenv import load_dotenv
load_dotenv()                                   # first line of src/web/config.py
backend = os.getenv("LLM_BACKEND", "ollama")
netbox_config = load_netbox_config() if backend == "llamacpp" else load_config()[1]

# CRITICAL: ONE llama-server slot. scripts/serve_qwen4exp.sh has no --parallel. Two concurrent
# /v1/chat/completions requests are queued by the server and, worse, thrash the prompt cache
# (85% of prompt tokens are normally cache hits). Serialise turns in the back end with one
# asyncio.Lock and tell waiting clients their queue position.

# CRITICAL: the MCP client is a stdio subprocess (langchain_mcp_adapters MultiServerMCPClient);
# AGENTS.md section 6 says keep concurrency at 1. Same lock covers it.

# CRITICAL: silent empty reply. Qwen3.8-Flash-Next emits reasoning_content first; when reasoning
# eats max_tokens the response has finish_reason="length" and NO visible content. query()'s
# filter (netbox_agent.py:466-471) then yields nothing. In stream_events(), read
# chunk.response_metadata.get("finish_reason") from the LAST AIMessageChunk of each model call and
# emit an "error" chunk when it is "length" and the turn produced no text. The client-side
# mitigation already exists: LLAMACPP_REASONING_EFFORT defaults to "low" (llamacpp_config.py:111).

# CRITICAL: stream_mode="messages" makes LangGraph call the model with streaming=True. That is a
# DIFFERENT llama-server code path (incremental tool-call parsing under --jinja) than the
# non-streaming call query() makes today. Verify in Gate 3 that tool calls still parse
# (tool_call_chunks assemble, args are valid JSON) on a two-step query. If they do not, fall back to
# stream_mode=["updates"] only (per-message granularity, no token deltas) and record it.

# GOTCHA: with stream_mode as a list, every yielded item is a 2-tuple (mode, payload).
#   "messages" -> (AIMessageChunk | ToolMessage, metadata_dict); metadata["langgraph_node"] is "model"/"tools"
#   "updates"  -> {"model": {"messages": [AIMessage]}} or {"tools": {"messages": [ToolMessage, ...]}}
#   Middleware hook nodes appear as "<Name>.before_model"; ignore anything that is not model/tools.
# Do NOT branch on node names beyond that; classify by message type and .tool_calls.

# GOTCHA: ToolMessage.content for our wrapped tools is a STRING starting with
# "TOOL_VALIDATION_ERROR:" or "TOOL_API_ERROR:" on failure (netbox_tools.py wrapper). Raw
# success content can be hundreds of KB (large_tool_results/ exists for this reason) - truncate
# to ~2 KB before sending to the browser; the model already got the full thing.

# GOTCHA: create_llamacpp_model(validate=True) runs a SYNC llm.invoke("test") inside async
# initialize(). Gate it with LLAMACPP_VALIDATE_ON_INIT (default "true" so the CLI keeps its
# behaviour); src/web sets it to "false" in its own process before building the agent.

# GOTCHA: InMemorySaver is process-local. Restarting the back end forgets every thread, but the
# browser still has the transcript in localStorage. On WebSocket (re)connect the client sends
# {"type":"resume","conversation_id":...}; the server answers {"type":"resumed",
# "metadata":{"known": false, "turns": 0}} and the UI shows "server memory lost - continue as new".

# GOTCHA: cancelling. asyncio.Task.cancel() on the task consuming agent.astream() closes the
# httpx stream -> llama-server aborts the generation and frees the slot. The checkpointer keeps
# the state as of the last completed node; the partial assistant text is NOT in the thread. Tell
# the user ("cancelled - the model will not remember this partial answer").

# GOTCHA: turns last minutes. Keep uvicorn ws pings on (defaults 20 s) and send a
# {"type":"status"} heartbeat chunk every 15 s while a turn is running or queued so the UI can
# show elapsed time and the proxy-free connection stays warm. Browsers do not time out WS.

# GOTCHA: switching between conversations is cheap for LangGraph but invalidates llama-server's
# prompt-prefix cache (different history = different prefix), so the next turn pays a cold prefill
# (measured 81.8 s for an 8.7k-token cold prefill). Not a bug; mention it in the UI hint.

# GOTCHA (claude-agentic-sdk lesson): NETBOX_TOKEN exported in the shell overrides .env and is
# inherited by the MCP stdio subprocess -> 403s. Document `env | grep NETBOX` in the run book.

# GOTCHA (claude-agentic-sdk lesson): four different backend ports across their README, nuxt.config,
# api.py and .env.anonymization. Here: 8010 backend, 3010 frontend, defined once in
# src/web/config.py (WEB_PORT) and once in frontend/nuxt.config.ts (NUXT_PUBLIC_WS_URL default).

# GOTCHA: langchain-openai 1.2.1 ChatOpenAI does not surface reasoning_content. No "thinking"
# chunks in this PRP. If wanted later: subclass ChatOpenAI or use a provider package.

# CRITICAL: token counts are OFF by default on this backend. ChatOpenAI only auto-enables
# stream_usage for the default OpenAI URL; with base_url set it sends no stream_options and
# llama-server sends no usage. Pass stream_usage=True in create_llamacpp_model(). Without it every
# usage_metadata is None and the whole ledger silently shows zeros.

# GOTCHA: the usage arrives as its OWN AIMessageChunk with content="" and usage_metadata set
# (base.py:1344), AFTER the chunk that carries finish_reason. Treat "usage_metadata is not None"
# as the end-of-model-call marker; do not expect it on the same chunk as finish_reason.

# GOTCHA: completion_tokens INCLUDES reasoning tokens (Qwen thinks before it answers). A call
# with output_tokens=1,900 and 40 visible characters is normal; show "tokens written" not "answer
# tokens". This is also why the length-budget failure looks like "1 call, 8192 out, 0 chars".

# GOTCHA: input_tokens is NOT monotonic across a turn. It grows call by call as tool results are
# appended (call 1: 9,280; call 2: 11,904 ...), and DROPS when SummarizationMiddleware compacts.
# The context gauge must show the LAST call's input_tokens, never the max or the sum.
# Compaction detection: primary = input_tokens of call N+1 < 0.8 x call N; secondary = an
# "updates" payload from a node whose name starts with "SummarizationMiddleware". Emit ONE
# context_compacted chunk per turn, not one per signal.

# GOTCHA: cache_read (prompt_tokens_details.cached_tokens) is what makes multi-turn affordable:
# measured 85% of prompt tokens are cache hits when the SAME thread continues, ~0% right after
# switching conversations. Show "read 46,376 (cached 39,600)" so the user sees why a resumed
# conversation is fast and a switched one is slow.

# GOTCHA: llama.cpp `timings` (prompt_per_second, predicted_per_second) are the only honest
# tok/s. Wall-clock / output_tokens is wrong by the tool-execution time and the prefill time.
# Get timings via the LlamaCppChatOpenAI subclass (Task 2); if the subclass is skipped, the UI
# must label its number "effective tok/s" and the ledger omits prefill speed.

# GOTCHA: DO NOT use count_tokens_approximately() or tiktoken for any UI number - the system
# prompt, tool schemas and skills are injected at call time, so state["messages"] undercounts
# ~19x (run_session.py:40-50). Server-reported usage or nothing.

# GOTCHA: Nuxt 3 nitro websocket flag (nitro.experimental.websocket) is only needed if Nuxt itself
# serves WS. Here the browser connects straight to FastAPI (no proxy), same as claude-agentic-sdk,
# so CORS on FastAPI must list http://localhost:3010 and http://127.0.0.1:3010.
```

## Implementation Blueprint

### Architecture
```
Browser (Nuxt 3 :3010)                    FastAPI (src/web :8010)                      Existing agent
+----------------------+   ws://.../ws/chat  +---------------------------+            +----------------------+
| useChatSocket        |<------------------->| /ws/chat                  |  stream_   | NetBoxDeepAgent      |
| useConversations     |   JSON StreamChunk  |  ClientMessage -> TurnRunner|  events() | (one instance)       |
| useServerStatus      |-- GET /status ----->|  asyncio.Lock (1 turn)     |----------->|  create_deep_agent   |
| ToolActivity         |-- GET /conversations|  cancel via Task.cancel()  |            |  InMemorySaver       |
+----------------------+   /{id}/messages    |  /health /status /models   |            |  thread_id = conv id |
                                             +---------------------------+            +----------+-----------+
                                                   | httpx GET /health,/slots                    | ChatOpenAI streaming
                                                   v                                             v
                                             llama-server 127.0.0.1:58123  (one slot, -c 131072, --jinja)  <- scripts/serve_qwen4exp.sh
                                                                                                 |
                                                                              NetBox MCP (stdio) + GraphQL -> NetBox :8000 (read-only token)
```

### Data models and structure

```python
# src/web/models.py
from datetime import UTC, datetime
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator

ChunkType = Literal[
    "connected",     # after WS accept; metadata: {"model": alias, "backend": "llamacpp"}
    "resumed",       # reply to resume; metadata: {"known": bool, "turns": int}
    "queued",        # sent once per turn; metadata: {"position": int} = turns AHEAD (0 = starts now)
    "status",        # heartbeat every 15 s; metadata: {"elapsed_s": float, "phase": "queued"|"running"}
    "text",          # token delta (content is the delta, NOT cumulative)
    "tool_use",      # metadata: {"call_id", "name", "args": dict}
    "tool_result",   # metadata: {"call_id", "name", "status": "ok"|"validation_error"|"api_error", "truncated": bool}
    "usage",         # one per model call; metadata: {"call_index", "input_tokens", "output_tokens", "cache_read",
                     #   "n_ctx", "context_pct", "prefill_tps", "decode_tps", "prompt_ms", "predicted_ms"}  (tps/ms None without timings)
    "context_compacted",  # once per turn when the middleware summarised; metadata: {"before_tokens", "after_tokens"}
    "done",          # completed=True; metadata: {"elapsed_s", "tool_calls", "model_calls", "finish_reason", "thread_id", "chars",
                     #   "usage": TurnUsage.model_dump()}
    "error",         # completed=True; content is user-safe text; metadata: {"kind": "length"|"agent"|"protocol"}
    "cancelled",     # completed=True
    "reset_complete",# after new_conversation; metadata: {"thread_id"}
]

class StreamChunk(BaseModel):
    """Server -> client. Same field set as claude-agentic-sdk/backend/models.py so the composable ports."""
    type: ChunkType
    content: str = ""
    completed: bool = False
    metadata: dict[str, Any] | None = None

class ClientMessage(BaseModel):
    """Client -> server. `message` kept for wire-compat with the claude-agentic-sdk CLI/composable."""
    type: Literal["message", "cancel", "new_conversation", "resume"] = "message"
    message: str | None = None
    conversation_id: str | None = None      # becomes the LangGraph thread_id

    @field_validator("message")
    @classmethod
    def strip_message(cls, v: str | None) -> str | None:
        return v.strip() if v is not None else v

class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    service: str = "netbox-web-chat"
    agent_ready: bool
    llama_ok: bool

class StatusResponse(BaseModel):
    model: str; backend: str; n_ctx: int | None
    compaction_trigger_tokens: int | None   # int(0.85 * n_ctx) - the DeepAgents fraction default
    slot_busy: bool | None; prompt_cache_tokens: int | None
    turn_running: bool; queue_depth: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class CallUsage(BaseModel):
    """One model call, straight from AIMessageChunk.usage_metadata (+ timings when available)."""
    call_index: int
    input_tokens: int                  # resident context for this call (server-reported)
    output_tokens: int                 # includes reasoning tokens
    cache_read: int = 0                # prompt_tokens_details.cached_tokens
    prefill_tps: float | None = None   # timings.prompt_per_second
    decode_tps: float | None = None    # timings.predicted_per_second
    prompt_ms: float | None = None
    predicted_ms: float | None = None

class TurnUsage(BaseModel):
    """Per-turn roll-up sent in `done` and stored in the per-thread ledger."""
    calls: list[CallUsage] = []
    model_calls: int = 0
    prompt_tokens_total: int = 0       # sum of input_tokens over calls = tokens READ this turn
    cache_read_total: int = 0
    completion_tokens_total: int = 0   # tokens WRITTEN this turn
    context_start: int | None = None   # input_tokens of the first call
    context_end: int | None = None     # input_tokens of the last call -> the gauge value
    context_peak: int = 0
    compacted: bool = False
    elapsed_s: float = 0.0

class ConversationUsage(BaseModel):
    """GET /conversations/{id}/usage - cumulative over the thread's turns (process lifetime)."""
    thread_id: str
    turns: list[TurnUsage]
    prompt_tokens_total: int; cache_read_total: int; completion_tokens_total: int
    model_calls_total: int; elapsed_s_total: float
    context_end: int | None; n_ctx: int | None
```

```python
# src/web/events.py - the one genuinely new piece of logic
from dataclasses import dataclass, field

@dataclass
class TurnStats:
    text_chars: int = 0
    tool_calls: int = 0
    finish_reason: str | None = None
    usage: TurnUsage = field(default_factory=TurnUsage)
    n_ctx: int = 131072                # from /status probe, fallback LLAMACPP_N_CTX
    compaction_emitted: bool = False
```

### Ordered task list

```yaml
Task 1: Dependencies and config
MODIFY pyproject.toml:
  - ADD to [project.optional-dependencies] a "web" extra: fastapi>=0.115, "uvicorn[standard]>=0.30", websockets>=13
  - KEEP runtime deps unchanged (CLI users do not need FastAPI)
  - RUN ./venv/bin/pip install -e ".[web,dev]"
MODIFY .env.example:
  - ADD section "# Web chat (python -m src.web)": WEB_HOST=127.0.0.1, WEB_PORT=8010,
    WEB_CORS_ORIGINS=http://localhost:3010,http://127.0.0.1:3010, WEB_MAX_QUEUE=4,
    WEB_TOOL_RESULT_PREVIEW_CHARS=2000, WEB_HEARTBEAT_S=15
  - ADD the currently undocumented vars with their code defaults: LLAMACPP_N_CTX=131072,
    LLAMACPP_MAX_TOKENS=8192, LLAMACPP_REASONING_EFFORT=low, LLAMACPP_VALIDATE_ON_INIT=true, ENABLE_GRAPHQL=1
  - FIX the stale LLAMACPP_MODEL example to qwen3.8-flash-next-UD-Q4_K_XL and LLAMACPP_BASE_URL to :58123/v1
CREATE src/web/config.py:
  - FIRST STATEMENT after imports: load_dotenv()
  - class WebConfig(BaseModel): host, port, cors_origins: list[str], max_queue, tool_result_preview_chars,
    heartbeat_s, backend (= LLM_BACKEND), model_name (LLAMACPP_MODEL if llamacpp else OLLAMA_MODEL),
    llama_base_url (LLAMACPP_BASE_URL with trailing /v1 stripped for /health and /slots)
  - def load_web_config() -> tuple[WebConfig, NetBoxConfig]  # MIRROR src/main.py:242-252 branch exactly
  - __repr__ masks nothing here because WebConfig holds no secrets; NetBoxConfig is passed separately

Task 2: Gate the blocking validation invoke; turn on usage + timings
MODIFY src/agents/llamacpp_config.py:
  - IN create_llamacpp_model: replace `if validate:` with
    `if validate and os.getenv("LLAMACPP_VALIDATE_ON_INIT", "true").lower() not in ("0","false","no"):`
  - PRESERVE default behaviour for CLI and eval (env unset -> still validates)
  - src/web/__main__.py sets os.environ.setdefault("LLAMACPP_VALIDATE_ON_INIT", "false") before importing api
  - ADD `stream_usage=True` to the ChatOpenAI(...) kwargs. Streaming-only effect; the CLI's
    non-streaming invoke path is unchanged (non-streaming responses already carry usage).
  - ADD class LlamaCppChatOpenAI(ChatOpenAI) in the same file and construct THAT instead of ChatOpenAI:
      def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info):
          gen = super()._convert_chunk_to_generation_chunk(chunk, default_chunk_class, base_generation_info)
          if gen is not None and isinstance(chunk, dict) and chunk.get("timings"):
              gen.message.response_metadata["timings"] = chunk["timings"]   # llama.cpp extension
          return gen
    (signature verified in langchain_openai 1.2.1 base.py:1321; the usage-only chunk is built at :1344.
     The override is additive: if a future version renames the hook, mypy/ruff will not catch it - add a
     unit test that feeds a fake chunk dict with "timings" and asserts response_metadata["timings"].)
  - `timings` are only present on the final streamed chunk of a call - the same chunk that has usage_metadata.

Task 3: Streaming events on the agent
MODIFY src/agents/netbox_agent.py (ADD methods only; do not touch query()):
  - ADD `async def stream_events(self, user_query: str, thread_id: str) -> AsyncGenerator[tuple[str, Any], None]`
      * same RuntimeError guard as query()
      * config = {"configurable": {"thread_id": thread_id}}
      * `async for mode, payload in self.agent.astream(inputs, config=config, stream_mode=["messages", "updates"]): yield mode, payload`
      * metrics: increment total_queries / successful_queries / response_times exactly as query() does (copy the try/except/finally)
  - ADD `async def get_history(self, thread_id: str) -> list[dict]`:
      * state = await self.agent.aget_state({"configurable": {"thread_id": thread_id}})
      * messages = state.values.get("messages", []) if state and state.values else []
      * return [{"role": "user"|"assistant", "content": m.content} for human messages and AI messages with content and no tool_calls]
  - ADD `def turn_count(self, thread_id) -> int` helper if cheap; otherwise derive from get_history

Task 4: Translate LangGraph stream into chunks
CREATE src/web/events.py:
  - def translate(mode, payload, stats: TurnStats, preview_chars: int) -> list[StreamChunk]
  - "messages": (msg, meta)
      * isinstance AIMessageChunk and msg.content (str) -> text chunk with delta; stats.text_chars += len
        (content may also be a list of blocks in langchain-core 1.x; join block["text"] for dict blocks with type "text")
      * fr = msg.response_metadata.get("finish_reason"); if fr: stats.finish_reason = fr
      * um = msg.usage_metadata; if um: -> END OF ONE MODEL CALL:
          cu = CallUsage(call_index=len(stats.usage.calls)+1, input_tokens=um["input_tokens"],
                         output_tokens=um["output_tokens"],
                         cache_read=(um.get("input_token_details") or {}).get("cache_read", 0),
                         prefill_tps=timings.get("prompt_per_second"), decode_tps=timings.get("predicted_per_second"),
                         prompt_ms=timings.get("prompt_ms"), predicted_ms=timings.get("predicted_ms"))
          where timings = msg.response_metadata.get("timings") or {}
          roll into stats.usage (model_calls, totals, context_start/end/peak)
          compaction check: prev = stats.usage.calls[-2].input_tokens if len>=2; if prev and cu.input_tokens < 0.8*prev
            and not stats.compaction_emitted -> emit context_compacted(before=prev, after=cu.input_tokens); stats.usage.compacted=True
          emit usage chunk with metadata = cu.model_dump() | {"n_ctx": stats.n_ctx, "context_pct": round(100*cu.input_tokens/stats.n_ctx, 1)}
      * ToolMessage arriving via "messages" mode: IGNORE here (handled in updates) to avoid duplicates
  - "updates": {node: delta}
      * for each AIMessage in delta["messages"] with .tool_calls: one tool_use chunk per call
        (metadata call_id=tc["id"], name=tc["name"], args=tc["args"]); stats.tool_calls += len
      * for each ToolMessage: status = "validation_error" if content.startswith("TOOL_VALIDATION_ERROR:")
        else "api_error" if content.startswith("TOOL_API_ERROR:") else "ok";
        content preview = first preview_chars chars, metadata.truncated = len(content) > preview_chars,
        call_id = msg.tool_call_id, name = msg.name
      * nodes whose name starts with "SummarizationMiddleware": set a pending-compaction flag (secondary signal);
        the usage handler above confirms it with the token drop and emits the chunk. Ignore every other dotted node.
  - def finish(stats, elapsed_s, thread_id) -> StreamChunk:
      * stats.usage.elapsed_s = elapsed_s
      * if stats.finish_reason == "length" and stats.text_chars == 0:
          error chunk, kind="length", content="The model used its whole output budget on reasoning and produced no answer. Try again, or start a new conversation. (LLAMACPP_REASONING_EFFORT / LLAMACPP_MAX_TOKENS)"
          metadata also carries "usage" so the footer can show the 8192-out / 0-chars evidence
      * else done chunk with metadata {elapsed_s, tool_calls, model_calls, finish_reason, thread_id, chars, usage: stats.usage.model_dump()}
  - PATTERN: pure functions, no I/O - unit-testable with hand-built AIMessageChunk/ToolMessage objects

Task 5: Turn runner (serialisation, queue, cancel)
CREATE src/web/session.py:
  - class TurnRunner:
      __init__(agent: NetBoxDeepAgent, config: WebConfig)
      self._lock = asyncio.Lock(); self._waiting: int = 0; self._current: asyncio.Task | None; self._current_ws_id
    async def run(self, ws_send, conversation_id: str, text: str) -> None:
      - if self._waiting >= config.max_queue: send error(kind="protocol", "server queue full") and return
      - ahead = self._waiting + (1 if a turn is running else 0); self._waiting += 1; send queued(position=ahead)
        (position is turns AHEAD, 0 when the turn starts immediately - the UI hides the queue notice at 0)
      - heartbeat task: every heartbeat_s send status(phase="queued"|"running", elapsed_s)
      - async with self._lock:
          self._waiting -= 1; start = monotonic(); stats = TurnStats()
          self._current = asyncio.current_task()
          try:
              async for mode, payload in agent.stream_events(text, conversation_id):
                  for chunk in translate(mode, payload, stats, preview): await ws_send(chunk)
              await ws_send(finish(stats, monotonic()-start, conversation_id))
          except asyncio.CancelledError:
              await ws_send(StreamChunk(type="cancelled", completed=True, content="Cancelled. The model will not remember this partial answer."))
              # do NOT re-raise if the cancel came from the user (flag set by cancel()); re-raise on shutdown
          except Exception as e:   # PATTERN: mirror query()'s filter-error branch; log with structlog
              await ws_send(StreamChunk(type="error", completed=True, content=sanitise(str(e)), metadata={"kind": "agent"}))
          finally: heartbeat.cancel(); self._current = None
    def cancel(self) -> bool: if self._current: self._user_cancel = True; self._current.cancel(); return True
    @property running / queue_depth
  - Usage ledger: self._ledger: dict[str, list[TurnUsage]] keyed by conversation_id. Append stats.usage in
    finally (also on cancel/error - partial calls still cost tokens). Bounded: keep the last 200 turns per
    thread. Process-local like InMemorySaver; the browser persists its own copy in localStorage.
  - def conversation_usage(self, cid) -> ConversationUsage: sums over the ledger; context_end = last turn's context_end
  - n_ctx for TurnStats: read once from the /slots probe at startup (Task 6), fallback int(os.getenv("LLAMACPP_N_CTX","131072"))
  - CRITICAL: only the WebSocket that started the turn may cancel it (compare ws ids); a second tab cannot kill the first tab's turn.
  - CRITICAL: run() is awaited inside the WS receive loop of the caller? NO - spawn it as a task so the
    loop can still receive "cancel" while the turn is running. Keep one in-flight task per WebSocket;
    reject a second "message" from the same socket with an error chunk until "done".

Task 6: llama-server status probe
CREATE src/web/llama_status.py:
  - async def probe(base_url: str) -> dict: httpx.AsyncClient(timeout=2.0); GET {base}/health -> ok bool;
    GET {base}/slots -> first slot: is_processing, n_ctx, n_prompt_tokens_cache; swallow ConnectError -> {"ok": False}
  - base_url is LLAMACPP_BASE_URL minus a trailing "/v1" (the /health and /slots routes are NOT under /v1)
  - if backend != "llamacpp": return {"ok": None} (status endpoint reports "n/a")

Task 7: FastAPI app
CREATE src/web/api.py (MIRROR claude-agentic-sdk/backend/api.py structure):
  - lifespan: web_config, netbox_config = load_web_config(); setup_logging(); agent = await create_netbox_agent(
      netbox_config=netbox_config, model_name=web_config.model_name, backend=web_config.backend);
      app.state.agent = agent; app.state.runner = TurnRunner(agent, web_config); yield; await agent.cleanup()
  - app = FastAPI(title="NetBox Web Chat", version="0.1.0", lifespan=lifespan)
  - CORSMiddleware(allow_origins=web_config.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    (NOTE: the claude app parsed CORS_ORIGINS but hardcoded the list - do not repeat that)
  - GET /health -> HealthResponse (agent_ready = app.state.agent.agent is not None; llama_ok from probe)
  - GET /status -> StatusResponse (probe + runner.running + runner.queue_depth)
  - GET /models -> [{"id": alias, "provider": "llamacpp", "available": True}] from get_llamacpp_models(); display only
  - GET /conversations/{conversation_id}/messages -> list[HistoryMessage] via agent.get_history (404 if empty)
  - GET /conversations/{conversation_id}/usage -> ConversationUsage from runner.conversation_usage (200 with zeros if unknown)
  - /status adds compaction_trigger_tokens = int(0.85 * n_ctx) so the gauge marker and the backend agree on one number
  - WS /ws/chat:
      accept; send connected(metadata={"model": alias, "backend": backend})
      loop: raw = await ws.receive_text(); msg = ClientMessage.model_validate_json(raw) (ValidationError -> error chunk, continue)
        "resume": turns = len(await agent.get_history(cid)); send resumed(known=turns>0, turns)
        "new_conversation": new id = uuid4().hex (server-generated so it is a valid thread id); send reset_complete(thread_id)
        "cancel": runner.cancel(ws_id) -> if False send error("nothing to cancel")
        "message": require conversation_id and non-empty message; if a turn task for this ws exists -> error;
                   task = asyncio.create_task(runner.run(ws.send_json-wrapper, cid, text))
      except WebSocketDisconnect: if this ws owns the running turn -> runner.cancel(ws_id) (frees the slot)
  - ws_send wrapper: `await ws.send_json(chunk.model_dump(mode="json"))`; catch RuntimeError/WebSocketDisconnect once and stop sending
  - Bind host from WEB_HOST (default 127.0.0.1). This is a single-operator tool; no auth.
CREATE src/web/__main__.py:
  - os.environ.setdefault("LLAMACPP_VALIDATE_ON_INIT", "false"); from .api import app; uvicorn.run(app, host, port, ws_ping_interval=20, ws_ping_timeout=60)
CREATE src/web/__init__.py (empty)

Task 8: WebSocket smoke client (protocol test without a browser)
CREATE scripts/ws_smoke.py (ADAPT claude-agentic-sdk/netbox_cli.py; keep --url, --json, -i):
  - default --url ws://127.0.0.1:8010/ws/chat
  - sends {"type":"message","conversation_id": <uuid>, "message": "..."}; prints text deltas inline, tool_use/tool_result
    as one line each, each usage chunk as "[call 2] ctx 11,904 (cached 9,280) out 412 | prefill 126.4 t/s decode 10.8 t/s",
    context_compacted as a banner, and done/error metadata as a final summary line incl. TurnUsage totals
  - --usage: after the turn, GET /conversations/<id>/usage and print the ledger table
  - --cancel-after N: send {"type":"cancel"} N seconds in; assert a "cancelled" chunk arrives
  - --follow-up "text": second message on the same conversation_id (memory check)
  - This is Gate 3's tool and the reference client for the protocol.

Task 9: Frontend scaffold (COPY, then edit)
  - cp -r /home/ola/dev/netboxdev/claude-agentic-sdk/frontend ./frontend EXCLUDING node_modules .nuxt .output .env .env.anonymization
  - frontend/package.json: name "netbox-web-chat"; keep nuxt ^3.14, vue, marked, dompurify, isomorphic-dompurify, highlight.js, @nuxtjs/tailwindcss, vue-tsc
  - frontend/nuxt.config.ts: wsUrl default ws://localhost:8010/ws/chat, apiUrl http://localhost:8010, devServer.port 3010; keep typescript.strict
  - frontend/.env.example: NUXT_PUBLIC_WS_URL, NUXT_PUBLIC_API_URL, PORT=3010
  - DELETE composables/useModelSelection.ts and components/ModelSelector.vue (one local model; no switching)
  - RUN npm install

Task 10: Types and socket composable
MODIFY frontend/types/chat.ts:
  - StreamChunk.type union = the 11 ChunkType strings from src/web/models.py
  - WebSocketMessage = { type: 'message'|'cancel'|'new_conversation'|'resume', message?: string, conversation_id?: string }
  - ToolCall { callId, name, args, status: 'pending'|'ok'|'validation_error'|'api_error', preview?, truncated? }
  - CallUsage { callIndex, inputTokens, outputTokens, cacheRead, prefillTps?, decodeTps?, promptMs?, predictedMs? }
  - TurnUsage { calls: CallUsage[], modelCalls, promptTokensTotal, cacheReadTotal, completionTokensTotal,
                contextStart?, contextEnd?, contextPeak, compacted, elapsedS }
  - TurnMeta { elapsedS, toolCalls, modelCalls, finishReason, chars, usage: TurnUsage }
  - ServerStatus { model, backend, nCtx, compactionTriggerTokens, slotBusy, promptCacheTokens, turnRunning, queueDepth }
MODIFY frontend/composables/useChatSocket.ts:
  - KEEP connect/reconnect/onMounted/onUnmounted structure (MAX_RECONNECT_ATTEMPTS, RECONNECT_DELAY_MS)
  - MAKE state module-level singletons (the claude app creates a new socket per caller - ConversationSidebar opened a 2nd socket)
  - handleStreamChunk:
      text -> append delta to currentAssistantMessage (deltas, not cumulative)
      tool_use -> push ToolCall(pending) into currentToolCalls
      tool_result -> find by callId, set status/preview
      usage -> push CallUsage into currentUsage.calls; update liveContextTokens (= this call's inputTokens),
               liveContextPct; running totals for the in-flight footer
      context_compacted -> push a divider entry {kind:'compaction', before, after} into the transcript
      queued/status -> queuePosition, phase, elapsedS
      done -> finalise message {role:'assistant', content, toolCalls, meta}; isProcessing=false
      error -> if kind==='length' push assistant message with the warning text and meta; else existing error path
      cancelled -> push assistant message "(cancelled)" with what streamed so far
      resumed -> set serverKnowsThread; if !known && localMessages.length -> show banner
      reset_complete -> handled by caller (updates conversation id)
  - sendMessage(text, conversationId); cancel(); newConversation() -> resolves with server thread_id; resume(conversationId)
  - on 'open': if active conversation -> resume(id) (replaces the claude app's switchModel-on-open)

Task 11: Conversations composable
MODIFY frontend/composables/useConversations.ts:
  - KEEP singleton refs + localStorage key (rename to 'netbox-web-chat-conversations' to avoid clashing with the claude app on the same origin)
  - Conversation.id MUST be the server thread_id: createConversation() awaits socket.newConversation() and stores the returned id
    (client-generated 'conv_<ts>' ids are fine for LangGraph too, but one id space is simpler - use the server's)
  - messages[] persist toolCalls + meta (incl. usage) so the tool panel and ledger survive reload
  - Conversation gains usage: { promptTokensTotal, cacheReadTotal, completionTokensTotal, modelCallsTotal,
    elapsedSTotal, contextEnd } recomputed from messages[].meta.usage on every finalise (single source: the messages)
  - On resume with resumed.known === true, GET /conversations/{id}/usage and prefer the server ledger if it has more turns

Task 12: Components
MODIFY components/ChatMessage.vue: render meta footer via new TurnFooter.vue; keep formatMarkdown pipeline
CREATE components/ToolActivity.vue: list of ToolCall rows for the in-flight or selected message; status pill; click -> expand preview (pre, monospace)
CREATE components/TurnFooter.vue: one line, e.g.
    "91.6 s · 3 model calls · 4 tools · in 33,120 (cached 27,900) · out 1,412 · ctx 12,450 (9.5%) · prefill 126 t/s · decode 10.8 t/s"
  - tokens formatted with thousands separators; tps hidden (not "0") when timings are absent; budget warning in red when finishReason==='length'
  - expandable: per-call table (call #, ctx in, cached, out, prefill t/s, decode t/s, prompt ms, predicted ms)
  - while streaming, the same footer renders from currentUsage and updates on every usage chunk
CREATE components/ContextGauge.vue (in the conversation header):
  - bar = contextEnd / nCtx; marker at compactionTriggerTokens; label "46,376 / 131,072 (35%)"
  - colour: <50% neutral, 50-85% amber, >=85% red; tooltip explains decode slows as context grows
    (measured 14.8 -> 12.6 t/s over 9k->46k; 5.1 -> 1.45 t/s by 76k) and that "New conversation" resets it
  - shows "n/a" until the first usage chunk of the conversation; live-updates during a turn from liveContextTokens
CREATE components/TokenLedger.vue (collapsible panel under the sidebar or header):
  - conversation totals: read / cached / written / model calls / wall time; per-turn rows (turn #, in, out, ctx end, s)
  - a "compacted" badge on turns where usage.compacted; sum row must equal the sum of usage chunks (unit-tested in TS if a test runner is added; otherwise Gate 4 manual)
CREATE components/CompactionDivider.vue: transcript divider "Context compacted: 112,340 -> 41,208 tokens"
MODIFY components/ConnectionStatus.vue: add a second indicator fed by useServerStatus (model alias, slot busy, queue depth)
CREATE composables/useServerStatus.ts: $fetch(`${apiUrl}/status`) every 10 s while a turn runs, every 60 s idle
MODIFY components/ChatInput.vue: when isProcessing, the send button becomes "Stop" -> emits cancel
MODIFY components/ConversationSidebar.vue: "New conversation" calls createConversation(); tooltip "Starts a clean thread - use this when an answer seems to reuse data from an earlier question"
MODIFY pages/index.vue: wire the above; keep the isLoadingMessages watch-guard pattern; drop model selector; show the "server memory lost" banner from resumed.known === false

Task 13: Backend tests
CREATE tests/test_web_events.py:
  - text delta from AIMessageChunk(content="Hel") -> one text chunk "Hel"
  - updates {"model": {"messages": [AIMessage(content="", tool_calls=[{id,name,args}])]}} -> tool_use with name/args
  - updates {"tools": {"messages": [ToolMessage(content="TOOL_VALIDATION_ERROR: ...", tool_call_id=..)]}} -> tool_result status validation_error
  - 5000-char ok result -> preview 2000 chars, truncated True
  - finish(stats with finish_reason="length", text_chars=0) -> error kind length; with text -> done
  - middleware node "FilterErrorRecoveryMiddleware.after_model" -> no chunks
  - AIMessageChunk(content="", usage_metadata={"input_tokens": 9280, "output_tokens": 412, "total_tokens": 9692,
      "input_token_details": {"cache_read": 7900}}, response_metadata={"timings": {"prompt_per_second": 126.4,
      "predicted_per_second": 10.8, "prompt_ms": 875.4, "predicted_ms": 38148.0}})
      -> one usage chunk with call_index 1, cache_read 7900, decode_tps 10.8, context_pct 7.1 (n_ctx 131072)
  - two usage chunks 12,000 then 4,000 -> context_compacted emitted once (before 12000, after 4000); a third at 4,500 emits nothing
  - usage without timings -> prefill_tps/decode_tps None (not 0)
  - finish() done.metadata["usage"] totals == sums of the calls; context_end == last call's input_tokens; context_peak == max
CREATE tests/test_llamacpp_config.py (small):
  - LlamaCppChatOpenAI._convert_chunk_to_generation_chunk with a fake dict containing "usage" and "timings"
    -> returned chunk has usage_metadata AND response_metadata["timings"]
  - create_llamacpp_model(validate=False) returns an instance with stream_usage is True
CREATE tests/test_web_session.py:
  - FakeAgent.stream_events yields (mode,payload) with awaits; two concurrent run() calls -> second sees queued(position=1) and its first text arrives after the first's done
  - cancel() mid-stream -> cancelled chunk, lock released, next run proceeds
  - max_queue exceeded -> error chunk
CREATE tests/test_web_api.py (PATTERN tests/test_netbox_integration.py: patch create_netbox_agent; FakeAgent on app.state):
  - GET /health 200 with llama probe patched
  - TestClient.websocket_connect("/ws/chat"): first frame is connected; send message -> receives text..., done
  - invalid JSON -> error kind protocol, socket stays open
  - resume unknown id -> resumed known=false
  - GET /conversations/{id}/messages 404 when empty, 200 list otherwise
  - GET /conversations/{id}/usage -> zeros for unknown id; after a FakeAgent turn that yields two usage chunks, totals add up
  - GET /status includes compaction_trigger_tokens == int(0.85 * n_ctx) with the probe patched to n_ctx=131072
  - NEVER hit llama-server or NetBox in unit tests

Task 14: Docs and run book
CREATE docs/setup/web-chat.md: three terminals (serve_qwen4exp.sh; ./venv/bin/python -m src.web; cd frontend && npm run dev), ports table, env vars, `env | grep NETBOX` check, known limits (single slot, memory lost on restart, no auth)
CREATE docs/development/2026-09-28_web-chat.md: decisions (why lock not --parallel; why messages+updates; why thread_id = conversation id; why no model switching; why no reasoning display) + ADD one line to docs/development/README.md
MODIFY CLAUDE.md "Architecture Overview" tree: add src/web/ and frontend/; "Running the System": add the two commands
MODIFY README.md: short "Web chat" section pointing at docs/setup/web-chat.md
MODIFY .gitignore: frontend/node_modules, frontend/.nuxt, frontend/.output, frontend/.env
```

### Per-task pseudocode

```python
# Task 3 - src/agents/netbox_agent.py (ADD; keep query() byte-identical)
async def stream_events(self, user_query: str, thread_id: str):
    if not self.agent:
        raise RuntimeError("Agent not initialized. Call initialize() first.")
    logger.info("Processing query (web)", query=user_query[:100], thread_id=thread_id[:8])
    start = time.time()
    config = {"configurable": {"thread_id": thread_id}}
    try:
        async for mode, payload in self.agent.astream(
            {"messages": [{"role": "user", "content": user_query}]},
            config=config,
            stream_mode=["messages", "updates"],   # token deltas + node-level messages
        ):
            yield mode, payload
        if self.metrics:
            self.metrics.successful_queries += 1
    except Exception as e:
        logger.error("Query failed (web)", error=str(e))
        if self.metrics and ("Invalid filter" in str(e) or "MCP Filter Error" in str(e)):
            self.metrics.filter_errors += 1
        raise
    finally:
        if self.metrics:
            self.metrics.total_queries += 1
            self.metrics.response_times.append(time.time() - start)

async def get_history(self, thread_id: str) -> list[dict[str, str]]:
    state = await self.agent.aget_state({"configurable": {"thread_id": thread_id}})
    out = []
    for m in (state.values.get("messages", []) if state and state.values else []):
        if m.type == "human":
            out.append({"role": "user", "content": _as_text(m.content)})
        elif m.type == "ai" and m.content and not getattr(m, "tool_calls", None):
            out.append({"role": "assistant", "content": _as_text(m.content)})
    return out
```

```python
# Task 4 - src/web/events.py
def translate(mode, payload, stats, preview_chars):
    chunks = []
    if mode == "messages":
        msg, meta = payload
        if isinstance(msg, AIMessageChunk):
            delta = _as_text(msg.content)            # str, or list of {"type":"text","text":...}
            if delta:
                stats.text_chars += len(delta)
                chunks.append(StreamChunk(type="text", content=delta))
            fr = (msg.response_metadata or {}).get("finish_reason")
            if fr:
                stats.finish_reason = fr              # last model call wins
    elif mode == "updates":
        for node, delta in payload.items():
            if "." in node or not isinstance(delta, dict):   # middleware hook nodes
                continue
            for m in delta.get("messages", []) or []:
                if isinstance(m, AIMessage) and m.tool_calls:
                    for tc in m.tool_calls:
                        stats.tool_calls += 1
                        chunks.append(StreamChunk(type="tool_use", content=tc["name"],
                            metadata={"call_id": tc["id"], "name": tc["name"], "args": tc["args"]}))
                elif isinstance(m, ToolMessage):
                    text = _as_text(m.content)
                    status = ("validation_error" if text.startswith("TOOL_VALIDATION_ERROR:")
                              else "api_error" if text.startswith("TOOL_API_ERROR:") else "ok")
                    chunks.append(StreamChunk(type="tool_result", content=text[:preview_chars],
                        metadata={"call_id": m.tool_call_id, "name": m.name, "status": status,
                                  "truncated": len(text) > preview_chars}))
    return chunks
```

```python
# Task 7 - src/web/api.py WebSocket loop (MIRROR claude-agentic-sdk/backend/api.py:143-315)
@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    await ws.accept()
    runner: TurnRunner = app.state.runner
    agent: NetBoxDeepAgent = app.state.agent
    ws_id = uuid.uuid4().hex
    turn: asyncio.Task | None = None
    send = _sender(ws)                                   # wraps ws.send_json(chunk.model_dump(mode="json"))
    await send(StreamChunk(type="connected", metadata={"model": agent.model_name, "backend": agent.backend}))
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = ClientMessage.model_validate_json(raw)
            except ValidationError as e:
                await send(StreamChunk(type="error", completed=True, content="Invalid message", metadata={"kind": "protocol"}))
                continue
            if msg.type == "resume":
                turns = len(await agent.get_history(msg.conversation_id)) if msg.conversation_id else 0
                await send(StreamChunk(type="resumed", metadata={"known": turns > 0, "turns": turns}))
            elif msg.type == "new_conversation":
                await send(StreamChunk(type="reset_complete", metadata={"thread_id": uuid.uuid4().hex}))
            elif msg.type == "cancel":
                if not runner.cancel(ws_id):
                    await send(StreamChunk(type="error", completed=True, content="Nothing to cancel", metadata={"kind": "protocol"}))
            else:  # "message"
                if turn and not turn.done():
                    await send(StreamChunk(type="error", completed=True, content="A turn is already running on this connection", metadata={"kind": "protocol"})); continue
                if not msg.message or not msg.conversation_id:
                    await send(StreamChunk(type="error", completed=True, content="message and conversation_id are required", metadata={"kind": "protocol"})); continue
                turn = asyncio.create_task(runner.run(send, ws_id, msg.conversation_id, msg.message))
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected", ws_id=ws_id[:8])
    finally:
        runner.cancel(ws_id)                             # frees the single slot if this socket owned the turn
        if turn: 
            with contextlib.suppress(asyncio.CancelledError): await turn
```

```typescript
// Task 10 - frontend/composables/useChatSocket.ts (delta accumulation; keep the claude app's connect/reconnect code)
case 'text':        currentAssistantMessage.value += chunk.content; break          // delta, not cumulative
case 'tool_use':    currentToolCalls.value.push({ callId: m.call_id, name: m.name, args: m.args, status: 'pending' }); break
case 'tool_result': { const tc = currentToolCalls.value.find(t => t.callId === m.call_id)
                      if (tc) { tc.status = m.status; tc.preview = chunk.content; tc.truncated = m.truncated } break }
case 'queued':      queuePosition.value = m.position; break
case 'status':      elapsedS.value = m.elapsed_s; phase.value = m.phase; break
case 'done':        finaliseAssistant({ elapsedS: m.elapsed_s, toolCalls: m.tool_calls, finishReason: m.finish_reason, chars: m.chars }); break
case 'error':       if (m?.kind === 'length') finaliseAssistant(undefined, chunk.content) else pushError(chunk.content); break
case 'cancelled':   finaliseAssistant(undefined, '(cancelled)'); break
case 'resumed':     serverKnowsThread.value = m.known; break
```

### Integration Points
```yaml
CONFIG (.env):
  WEB_HOST=127.0.0.1
  WEB_PORT=8010
  WEB_CORS_ORIGINS=http://localhost:3010,http://127.0.0.1:3010
  WEB_MAX_QUEUE=4
  WEB_TOOL_RESULT_PREVIEW_CHARS=2000
  WEB_HEARTBEAT_S=15
  LLAMACPP_VALIDATE_ON_INIT=true        # src/web forces false in its own process
  # unchanged, already live: LLM_BACKEND=llamacpp, LLAMACPP_BASE_URL=http://localhost:58123/v1,
  # LLAMACPP_MODEL=qwen3.8-flash-next-UD-Q4_K_XL, LLAMACPP_REASONING_EFFORT=low, NETBOX_URL, NETBOX_TOKEN, MCP_SERVER_PATH

FRONTEND (frontend/.env):
  NUXT_PUBLIC_WS_URL=ws://localhost:8010/ws/chat
  NUXT_PUBLIC_API_URL=http://localhost:8010
  PORT=3010

PROCESSES:
  llama-server : scripts/serve_qwen4exp.sh            -> 127.0.0.1:58123  (one slot; first load pages ~105 GiB)
  backend      : ./venv/bin/python -m src.web         -> 127.0.0.1:8010
  frontend     : cd frontend && npm run dev            -> localhost:3010
  NetBox       : docker, :8000 (read-only llm-agent token)

ENTRY POINTS:
  python -m src.main      # CLI, unchanged
  python -m src.web       # new
  scripts/ws_smoke.py     # protocol client

AGENT SURFACE USED (no changes to behaviour):
  create_netbox_agent(netbox_config, model_name, backend)  -> NetBoxDeepAgent
  agent.stream_events(text, thread_id)   NEW
  agent.get_history(thread_id)           NEW
  agent.cleanup()
  agent.model_name, agent.backend, agent.metrics
```

## Validation Loop

### Gate 1 - syntax / style / types (must pass)
```bash
cd /home/ola/dev/netboxdev/ollamaDeepAgents
./venv/bin/pip install -e ".[web,dev]"
./venv/bin/ruff check src/web src/agents/netbox_agent.py src/agents/llamacpp_config.py scripts/ws_smoke.py tests/test_web_*.py --fix
./venv/bin/ruff format src/web tests/test_web_*.py scripts/ws_smoke.py
./venv/bin/mypy src/web
# Expected: no errors. mypy config is lenient (disallow_untyped_defs=false) but warn_return_any=true - annotate returns.
cd frontend && npm run build     # Nuxt build must succeed; vue-tsc typeCheck stays off as in the claude app
```

### Gate 2 - unit tests (fake agent, no llama-server, no NetBox)
```bash
./venv/bin/python -m pytest tests/test_web_events.py tests/test_web_session.py tests/test_web_api.py -v
./venv/bin/python -m pytest tests/test_netbox_integration.py tests/test_filters.py -v   # existing suites still green
# Expected: all pass. If a stream translation test fails, fix events.py - never widen the test to match.
```
```python
# tests/test_web_events.py - shape of the key cases
def test_text_delta():
    stats = TurnStats()
    out = translate("messages", (AIMessageChunk(content="Hel"), {"langgraph_node": "model"}), stats, 2000)
    assert [c.type for c in out] == ["text"] and out[0].content == "Hel" and stats.text_chars == 3

def test_tool_use_and_result():
    ai = AIMessage(content="", tool_calls=[{"id": "c1", "name": "netbox_get_objects", "args": {"object_type": "dcim.site"}}])
    tm = ToolMessage(content="TOOL_VALIDATION_ERROR: multi-hop filter", tool_call_id="c1", name="netbox_get_objects")
    stats = TurnStats()
    a = translate("updates", {"model": {"messages": [ai]}}, stats, 2000)
    b = translate("updates", {"tools": {"messages": [tm]}}, stats, 2000)
    assert a[0].type == "tool_use" and a[0].metadata["name"] == "netbox_get_objects"
    assert b[0].type == "tool_result" and b[0].metadata["status"] == "validation_error"

def test_length_with_no_text_is_error():
    stats = TurnStats(text_chars=0, finish_reason="length")
    assert finish(stats, 12.0, "t1").type == "error"

async def test_second_turn_queues(fake_agent):
    runner = TurnRunner(fake_agent, WebConfig(max_queue=4))
    sent_a, sent_b = [], []
    t1 = asyncio.create_task(runner.run(sent_a.append, "ws1", "conv1", "q1"))
    await asyncio.sleep(0)                       # t1 holds the lock
    t2 = asyncio.create_task(runner.run(sent_b.append, "ws2", "conv2", "q2"))
    await asyncio.gather(t1, t2)
    assert sent_b[0].type == "queued" and sent_b[0].metadata["position"] == 1
    assert sent_a[-1].type == "done"
```

### Gate 3 - integration against the real stack (protocol, streaming, tool-call parsing under streaming)
```bash
# Terminal 1 (skip if already up: curl -s 127.0.0.1:58123/health -> {"status":"ok"})
scripts/serve_qwen4exp.sh
# Terminal 2
env | grep -i netbox_token && echo "WARNING: shell NETBOX_TOKEN will override .env"   # claude-agentic-sdk lesson
./venv/bin/python -m src.web
# Terminal 3
curl -s 127.0.0.1:8010/health ; curl -s 127.0.0.1:8010/status
./venv/bin/python scripts/ws_smoke.py "List the sites for tenant Dunder-Mifflin with their status"
#   Expected: text deltas appear progressively (not one blob); at least one tool_use line
#   (netbox_get_objects or netbox_graphql); a done line with elapsed_s and tool_calls>0.
#   CHECK tool-call parsing under streaming: args in each tool_use must be a dict, and the result
#   status must be "ok" for a well-formed call. If args arrive mangled/empty, see the stream_mode gotcha
#   and fall back to ["updates"]; record the finding in docs/development/2026-09-28_web-chat.md.
#   CHECK usage: one "[call N]" line per model call with non-zero ctx and out; prefill/decode t/s present.
#   CROSS-CHECK context against the server (the ground-truth rule from run_session.py): in the
#   llama-server log the slot-release line for the turn's last call reads
#     "stop processing: n_tokens = <N>, truncated = 0"
#   and <N> must equal the last usage chunk's input_tokens + output_tokens (within 1%).
#   CROSS-CHECK cache: run the same follow-up twice on the same thread; second run's cache_read
#   should be >= 80% of input_tokens. Then switch to a fresh conversation_id: cache_read ~ 0.
./venv/bin/python scripts/ws_smoke.py "Say OK" --usage
#   Expected: ledger table prints; totals equal the sum of the printed [call N] lines.
./venv/bin/python scripts/ws_smoke.py "Show devices at site DM-Akron" --follow-up "How many of those are active?"
#   Expected: second answer references the first turn's device list (memory on the same thread).
./venv/bin/python scripts/ws_smoke.py "Describe every device, rack and prefix at every Dunder-Mifflin site" --cancel-after 20
#   Expected: cancelled chunk within ~2 s; curl -s 127.0.0.1:58123/slots | grep -o '"is_processing":[a-z]*' -> false
# Two clients at once (single slot): run two ws_smoke.py in parallel ->
#   second prints queued position 1, produces no text until the first prints done.
```

### Gate 4 - browser end-to-end
```bash
cd frontend && npm run dev          # http://localhost:3010
# 1. Send "What sites do I have?"  -> bubble streams; ToolActivity shows the call; footer shows elapsed + tool count.
# 2. Send a follow-up               -> answer uses previous context.
# 3. Click New conversation, repeat the follow-up -> the model no longer knows (it must look it up or say so).
# 4. Start a long query, click Stop  -> "(cancelled)" bubble; status bar shows slot free.
# 5. Second tab sends during a turn  -> "queued (1)" indicator; no interleaving.
# 6. Restart the backend, reload     -> banner "server memory lost - continue as new conversation".
# 7. Browser console and backend log clean of errors.
# 8. Token/context: after step 1 the TurnFooter shows in/out tokens and t/s; ContextGauge shows a
#    non-zero % that matches the last [call N] ctx from scripts/ws_smoke.py on the same thread.
# 9. Run 8-10 turns of the v5 questions down ONE conversation (tests/eval/run_session.py's list):
#    the gauge climbs turn by turn (expect ~9k -> ~46k, per docs/traces/2026-09-24_netbox-session_kvvram.md),
#    the ledger sum row equals the sum of turn rows, cached share is high after turn 1.
# 10. Optional long soak: keep going past ~111k (the 0.85 trigger has never fired in this project) ->
#     a CompactionDivider appears and the gauge drops. Record the before/after numbers in the decision
#     note; this is the first observation of compaction on this model.
```

### Gate 5 - agent behaviour unchanged (comparability)
```bash
git diff --stat src/agents/netbox_agent.py    # additions only; query(), NETBOX_SYSTEM_PROMPT, middleware untouched
./venv/bin/python -m tests.eval.run_session   # existing session harness still runs on the CLI path (needs NetBox + llama-server)
# No new benchmark claims are made in this PRP. If Gate 3 forced the ["updates"]-only fallback, say so in the decision note.
```

## Final validation Checklist
- [ ] Gate 1-5 pass; outputs recorded in `docs/development/2026-09-28_web-chat.md`
- [ ] `query()`, `NETBOX_SYSTEM_PROMPT`, middleware list, skills unchanged (diff shows additions only)
- [ ] Ports appear exactly once per side: `WEB_PORT` in `src/web/config.py`, `NUXT_PUBLIC_WS_URL` default in `frontend/nuxt.config.ts`
- [ ] `.env.example` documents every env var the web layer reads, plus the previously undocumented `LLAMACPP_*` ones
- [ ] `finish_reason == "length"` with no text renders as a visible warning, never an empty bubble
- [ ] `stream_usage=True` is set; a turn with zero `usage` chunks is treated as a bug, not "no data"
- [ ] Context gauge value cross-checked once against the llama-server `n_tokens` log line (Gate 3)
- [ ] Ledger totals equal the sum of per-call usage (unit test + Gate 4 step 9)
- [ ] Cancel frees the llama-server slot (verified via `/slots`)
- [ ] No secrets in `frontend/`; NetBox token never leaves the back end
- [ ] `conversation_history/` and `large_tool_results/` growth noted in the run book
- [ ] CLAUDE.md tree and README updated; `docs/development/README.md` has the new line

---

## Anti-Patterns to Avoid
- ❌ Don't create a second `NetBoxDeepAgent` per WebSocket (the claude app did one Claude session per socket - here that means a second MCP subprocess and a second checkpointer per tab). One agent, many `thread_id`s.
- ❌ Don't add `--parallel N` to `serve_qwen4exp.sh` to "fix" concurrency - it splits the KV budget per slot and is unmeasured on this model. Serialise in the back end.
- ❌ Don't modify `query()` or reuse it for the web path - the eval harness and CLI depend on its exact filtering.
- ❌ Don't send cumulative text; send deltas. Don't send full tool results; preview them.
- ❌ Don't branch on middleware node names; classify by message type.
- ❌ Don't raise `LLAMACPP_MAX_TOKENS` to fix empty answers (withdrawn claim, `llamacpp_config.py:73-89`); surface `finish_reason` instead.
- ❌ Don't call `load_config()` on the llamacpp backend; don't read `LLM_BACKEND` before `load_dotenv()`.
- ❌ Don't hardcode the CORS list while also parsing an env var (claude-agentic-sdk `api.py:83-89` vs `config.py:33`).
- ❌ Don't let a second socket cancel another socket's turn.
- ❌ Don't put a model selector in the UI - one model is loaded; `/models` is informational.
- ❌ Don't `break` out of `agent.astream()` on the first text (leaves the graph mid-run and the slot busy); let it finish or cancel the task.
- ❌ Don't estimate tokens client-side (tiktoken, `count_tokens_approximately`, chars/4) - server-reported usage only.
- ❌ Don't show the sum or max of a turn's `input_tokens` as "context"; it is the last call's value.
- ❌ Don't compute tok/s from wall time when `timings` are available; and never show "0 t/s" for missing data.
- ❌ Don't commit `frontend/.env`, `.nuxt/`, `node_modules/`.

## Out of scope (explicit)
Auth / multi-user isolation; durable checkpointer (SQLite/Postgres); model switching; reasoning/thinking display (blocked by `ChatOpenAI` dropping `reasoning_content` - although the `LlamaCppChatOpenAI` subclass from Task 2 is the natural place to add it later); message edit-and-resend (the claude app has it; port later if wanted); Playwright suite; Docker packaging; cost-in-currency estimates (local inference; show tokens and seconds, not dollars); splitting reasoning tokens from answer tokens (the server reports one `completion_tokens` figure).

## Future enhancements
1. `SqliteSaver` / `AsyncPostgresSaver` so conversations survive restarts and `resumed.known` is usually true.
2. `--reasoning-format` + a `ChatOpenAI` subclass to stream `reasoning_content` as `thinking` chunks (collapsed by default).
3. Prompt-cache-aware scheduling: prefer running the next turn of the *same* conversation before switching threads.
4. Persist per-turn stats to LangSmith metadata so the eval harness can compare CLI vs web transcripts; feed the same `usage` roll-up back into `tests/eval/run_session.py` to replace its log-scraping regexes.
5. Port the claude app's edit-and-resend once the history API can truncate a thread (`aupdate_state`).

## Confidence: 8/10
High because every integration surface is verified, not assumed: the agent already exposes `thread_id` memory and `aget_state`; LangGraph 1.2.5's `["messages","updates"]` tuple contract and the `model`/`tools` node names were read from the installed packages; `TOOL_VALIDATION_ERROR:`/`TOOL_API_ERROR:` prefixes, the `finish_reason` plumbing in `langchain-openai 1.2.1`, the single llama-server slot and its `/health` + `/slots` endpoints were all checked against the live install; the token path was exercised end to end on 2026-09-28 (a streamed request to the running server returned `usage` with `cached_tokens` plus `timings`, and the exact `ChatOpenAI` lines that map or drop those fields are cited); and the whole front end is a port of working code rather than a fresh design.
The -2: (1) `stream_mode="messages"` switches llama-server to its streaming tool-call parser, which this project has never exercised with Qwen3.8-Flash-Next under `--jinja` - Gate 3 tests it explicitly and the `["updates"]`-only fallback is specified, but if it fails the UX loses token deltas; (2) `asyncio.Task.cancel()` freeing the slot depends on `httpx`/`openai` closing the SSE stream promptly during a long decode - expected, but only Gate 3's `/slots` check proves it on this box.
