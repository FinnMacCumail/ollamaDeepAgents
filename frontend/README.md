# NetBox Web Chat - frontend

Nuxt 3 chat UI for the NetBox DeepAgents query system, talking to the FastAPI backend in
`src/web/` over a WebSocket. Ported from the `claude-agentic-sdk` frontend; the agent behind it
is the local llama.cpp-served Qwen3.8-Flash-Next, so turns take tens of seconds to minutes and the
UI is built around streaming, tool activity, cancellation and token/context accounting.

## Run

```bash
npm install
cp .env.example .env      # defaults: backend ws://localhost:8010, UI on 3010
npm run dev               # http://localhost:3010
```

The backend must be up first: `./venv/bin/python -m src.web` from the repo root (see
`docs/setup/web-chat.md`).

## What the UI shows

- Streaming assistant bubble (markdown + tables), user bubbles.
- Tool activity per turn: one row per NetBox tool call with ok / validation error / API error
  status and an expandable result preview.
- Turn footer: elapsed, model calls, tool calls, tokens read (and cached), tokens written, resident
  context with % of window, prefill and decode t/s from llama-server `timings`.
- Context gauge in the header: last call's prompt tokens vs `n_ctx`, compaction trigger marked.
- Token ledger in the sidebar: per-conversation totals and per-turn rows.
- "Context compacted" divider in the transcript when the middleware summarises.
- Stop button during a turn; New conversation; connection + model/slot status.

## Protocol (see `types/chat.ts` and `src/web/models.py`)

Client -> server:
```json
{"type": "message", "conversation_id": "<thread id>", "message": "..."}
{"type": "cancel"}
{"type": "new_conversation"}
{"type": "resume", "conversation_id": "<thread id>"}
```

Server -> client chunks: `{type, content, completed, metadata}` with `type` in
`connected, resumed, queued, status, text, tool_use, tool_result, usage, context_compacted,
done, error, cancelled, reset_complete`. `text` chunks are deltas.

## Layout

```
frontend/
├── components/   ChatHistory ChatInput ChatMessage ConnectionStatus ConversationSidebar
│                 ConversationItem LoadingSpinner ToolActivity TurnFooter ContextGauge
│                 TokenLedger CompactionDivider
├── composables/  useChatSocket (singleton socket)  useConversations (localStorage)  useServerStatus (/status poll)
├── pages/index.vue
├── types/chat.ts
└── utils/        formatters.ts (markdown, token/tps formatting)  storage.ts  debug.ts
```

## Build

```bash
npm run build
```

Conversations live in `localStorage` under `netbox-web-chat-conversations`; the backend's memory is
in-process, so after a backend restart the UI shows a "server memory lost" banner and you should
start a new conversation.
