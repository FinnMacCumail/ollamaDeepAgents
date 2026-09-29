# FEATURE

A web chat front end + HTTP/WebSocket back end for the existing NetBox DeepAgents query
system, running against the locally served **Qwen3.8-Flash-Next** (176B MoE, `qwen4exp`,
`unsloth/Qwen3.8-Flash-Next-GGUF:UD-Q4_K_XL`) on llama.cpp. Today the agent is reachable only
through `python -m src.main` (Rich CLI). The feature adds:

- `src/web/` - a FastAPI service that owns ONE long-lived `NetBoxDeepAgent` and exposes it over
  a WebSocket with token-level streaming, tool-activity events, cancellation and per-conversation
  memory (LangGraph `thread_id`).
- `frontend/` - a Nuxt 3 chat UI (mirroring the proven `claude-agentic-sdk` frontend): message
  history, live streaming, tool-call display, "new conversation", cancel, connection/model status,
  local conversation list.
- Token and context visibility: per turn, tokens read / cached / written per model call with
  llama.cpp prefill and decode tok/s; per conversation, a context gauge (last call's prompt tokens
  vs the 131072 window, compaction trigger marked) and a cumulative token ledger. Numbers must be
  server-reported (`usage` + `timings` from llama-server), never client-side estimates.

Hard constraints (carried over from CLAUDE.md / AGENTS.md):
- Read-only NetBox access (MCP read tools + GraphQL AST guard + read-only `llm-agent` token).
- Inference never leaves the box: `LLM_BACKEND=llamacpp`, server bound to 127.0.0.1.
- Existing CLI, eval harness (`tests/eval/`) and `NetBoxDeepAgent.query()` behaviour unchanged,
  so benchmark comparability against `netbox-benchmark-v5` is preserved.
- Single llama-server slot (no `--parallel`) and stdio MCP: the back end must serialise turns.

This is a single-operator LAN tool: no auth, no database, no multi-tenant isolation in this PRP.

# USER VALUE

As a network engineer using the local NetBox assistant,
I want a browser chat window instead of a terminal,
so that I can see the answer stream in as the model writes it (turns take 35 s - 8 min), watch
which NetBox tools are being called, stop a runaway turn, keep several conversations and start a
clean one when context contamination is suspected (the 0.750 -> 0.950 order-effect finding).

# NOTES FOR WHOEVER RUNS generate-prp

- Base the structure and depth on `/home/ola/dev/netboxdev/claude-agentic-sdk/PRPs/netbox-chatbox.md`
  (the Claude Agent SDK chatbox PRP) - same Goal/Why/What/Context/Blueprint/Validation shape - but
  swap ClaudeSDKClient for the existing `NetBoxDeepAgent` + LangGraph streaming.
- Reuse the claude-agentic-sdk frontend code (composables, components, formatters) rather than
  designing a new UI.
- Make no model-quality claims; this PRP is transport + UI. Do not touch `NETBOX_SYSTEM_PROMPT`.
