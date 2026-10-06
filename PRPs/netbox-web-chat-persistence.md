name: "Durable conversation memory for the NetBox web chat (SQLite checkpointer + cancel rollback)"
description: |
  Make the web chat's conversation memory survive backend restarts by giving the web path a
  SQLite-backed LangGraph checkpointer, and roll cancelled turns back so persistence does not
  make orphaned questions permanent. Everything the CLI and the evaluation harness use keeps the
  in-memory checkpointer and is byte-identical. Follows PRPs/netbox-web-chat.md in shape.

## Purpose
Return-to-conversation currently works only while the backend process lives. The browser keeps
the transcript in localStorage; the model's memory of it lives in `InMemorySaver` and dies with
the process. This PRP moves that memory to disk for the web path, keeps the existing
`thread_id` routing, and closes the one hole persistence would widen: cancelled turns.

## Core Principles
1. **Context is King**: every API, version and behaviour below was verified against `./venv` on 2026-10-05, not read from docs.
2. **Validation Loops**: fake-agent unit tests for mechanics, then a real restart test through the WebSocket smoke client.
3. **Information Dense**: identifiers are the real ones from `src/web/`, `src/agents/netbox_agent.py` and the installed packages.
4. **Progressive Success**: saver injection first (Tasks 1-4), cancel rollback second (5-6), resume hardening third (7), docs last.
5. **Global rules**: CLAUDE.md and AGENTS.md (read-only NetBox, `./venv/bin/python`, decision note in `docs/development/`, no commits unless asked).

---

## Goal
Restart `python -m src.web`, reopen a conversation in the browser, ask a follow-up that depends
on an earlier answer, and get it answered from memory without a NetBox lookup. The resume reply
says the server knows the thread. Cancelling a turn leaves the thread exactly as it was after the
last completed turn. `python -m src.main`, `tests/eval/run_session.py` and every existing test
behave as before.

## Why
- **Measured fault.** A -> B -> A within one process keeps A's memory (verified 2026-10-05:
  A's follow-up answered "DM-Akron (2)" from context with zero tool calls). The loss happens only
  across a restart, because `netbox_agent.py:290` constructs `InMemorySaver()`.
- **Persistence makes the cancel bug permanent.** Cancelling after the first tool result left
  the thread with the cancelled user message and no answer; the next turn ran clean but the
  orphan now sits in every later prompt (verified: history after cancel = `[user]`, after the
  next turn = `[user, user, assistant]`). LangGraph also leaves `state.next` pointing at the
  unfinished node. With a durable saver this survives forever unless rolled back.
- **The session-harness finding needs continuity.** Conversation hygiene is a correctness
  control (0.750 vs 0.950 by order); a conversation that silently loses memory on restart turns a
  continued thread into a cold one without telling the model.
- **ADR-0039 listed this as the first follow-up.** The ChatGPT report (2026-10-05) reached the
  same primary recommendation; this PRP takes its steps 1-4 and declines its larger catalogue /
  transcript-import design for a single-operator tool.

## What
### User-visible behaviour
- After a backend restart, an old conversation resumes with `known: true` and follow-ups work.
- The "server memory lost" banner appears only for conversations created before this change or
  whose database file was removed.
- Stop now reads "Cancelled. The thread was rolled back to your previous question." and the
  cancelled question no longer influences later answers. The cancelled user bubble stays in the
  browser transcript, marked cancelled, but is not in the model's history.
- Conversation delete in the sidebar also deletes the server thread.

### Technical requirements
- `NetBoxDeepAgent(checkpointer=...)` and `create_netbox_agent(checkpointer=...)`, default
  `InMemorySaver()` so all 20 existing callers are unchanged.
- `src/web/api.py` lifespan opens `AsyncSqliteSaver` on `WEB_CHECKPOINT_DB` (default
  `data/web_checkpoints.sqlite`), runs `setup()`, injects it, and fails startup if the file cannot
  be opened. No silent fallback to memory.
- New `NetBoxDeepAgent.rollback_turn(thread_id, keep_message_ids)` using `aupdate_state` with
  `RemoveMessage`, called by `TurnRunner` on user cancel and on agent error.
- `resumed` chunk carries `conversation_id`; frontend ignores replies for a thread it is no
  longer viewing.
- `DELETE /conversations/{id}` calls `saver.adelete_thread`.
- New dependency `langgraph-checkpoint-sqlite==3.1.1` in the `web` extra (brings `aiosqlite`,
  `sqlite-vec`; upgrades nothing already installed).

### Success Criteria
- [ ] Restart test: turn on thread A, restart backend, `resume` A -> `known: true`, follow-up answered with 0 tool calls.
- [ ] Cancel test: cancel after first tool result, then `GET /conversations/{id}/messages` returns only completed turns; the thread's `state.next` is empty; next turn's `context_end` is no larger than before the cancelled turn plus the new question.
- [ ] Startup with an unwritable `WEB_CHECKPOINT_DB` path exits non-zero with a clear log line.
- [ ] `python -m src.main` and `tests/test_netbox_integration.py` unchanged; `grep InMemorySaver src/agents/netbox_agent.py` still finds the default.
- [ ] Forced-compaction thread (or a seeded `_summarization_event`) reloads after restart with the same state values.
- [ ] `ruff`, `mypy src/web`, all `tests/test_web_*.py` pass; `npm run build` passes.

## All Needed Context

### Reconciliation with current reality (READ FIRST)
- **Installed in `./venv` (what runs):** deepagents 0.7.5, langgraph 1.2.5, langgraph-checkpoint
  4.1.1, langchain 1.3.14, langchain-openai 1.2.1. `uv.lock` says deepagents 0.7.14 / langgraph
  1.2.11 / langgraph-checkpoint 4.2.0 but was never installed; `.venv/` is a second, unused
  Python 3.13 environment. Use `./venv`.
- **`langgraph-checkpoint-sqlite==3.1.1`** requires `langgraph-checkpoint>=4.1.0,<5`,
  `aiosqlite>=0.20`, `sqlite-vec>=0.1.6`. `pip install --dry-run` against `./venv` reports
  langgraph-checkpoint 4.1.1 already satisfied; only the three new packages are added.
- **Round-trip verified** (saver 3.1.1 on langgraph 1.2.5): a graph with a `PrivateStateAttr`
  field like DeepAgents' `_summarization_event` was written by one saver instance and reloaded
  by a second over the same file with identical `values`, `next == ()`, then continued.
  `aget_state` on an unknown thread returns `values == {}`; `adelete_thread` empties it.
- **Cancel mechanics verified** (LangGraph 1.2.5 + InMemorySaver): checkpoints are written per
  step (`durability` default `"async"`), so a cancel mid-run leaves completed steps and
  `state.next == ('<node>',)`. A later call with new input is treated as a fresh run (the pending
  node is dropped, `pregel/_loop.py:_first`), so the orphaned messages remain and the pending
  node is never resumed. `aupdate_state(cfg, {"messages": [RemoveMessage(id=...)...]}, as_node=
  <last node>)` removed the orphans and cleared `next`; a following turn ran normally.
- **Message ids exist.** `add_messages` assigns a UUID to any message without one
  (`langgraph/graph/message.py:204`), so every message in state is removable by id.
- **Artifacts already persist.** `SummarizationMiddleware` writes
  `conversation_history/<thread_id>.md` and `large_tool_results/` under `PROJECT_ROOT`
  (`FilesystemBackend(root_dir=PROJECT_ROOT, virtual_mode=True)`, `netbox_agent.py:415`).
  3.2 MB and 27 MB today, gitignored. Nothing to change; back them up with the database.
- **AsyncSqliteSaver is one `aiosqlite` connection guarded by an `asyncio.Lock`.** Fine for this
  single-process, single-turn-at-a-time server; not a multi-worker design.
- **`resumed` has no thread id** (`api.py:228-233`), and the frontend writes it straight into
  `serverKnowsThread` (`useChatSocket.ts:183-186`). A slow reply for a previous selection can
  mislabel the current one.
- The frontend's `handleNewConversation` and sidebar delete are browser-only today.

### Documentation & References
```yaml
- file: src/agents/netbox_agent.py
  why: InMemorySaver at L290; create_deep_agent(checkpointer=...) at L428; stream_events L520; get_history L573; cleanup L647; factory L661.
  critical: 20 callers of NetBoxDeepAgent()/create_netbox_agent() across src/main.py, tests/, tests/eval/ - all must keep working with no new argument.

- file: src/web/api.py
  why: lifespan (builds agent, runner); resume handler L220-233; new_conversation L234-237; the WebSocket finally block.

- file: src/web/session.py
  why: TurnRunner.cancel L78-85; user-cancel branch sends the "will not remember" chunk; _terminal_meta.

- file: src/web/config.py
  why: WebConfig + load_web_config(); add checkpoint_db here, read WEB_CHECKPOINT_DB.

- file: frontend/composables/useChatSocket.ts
  why: resume() L452, setActiveThread() L458, 'resumed' handler L183; sendMessage payload L411.

- file: frontend/pages/index.vue
  why: showMemoryLostBanner computed L148-152; handleNewConversation L241.

- file: tests/test_web_api.py
  why: fixture patches api_module._build_agent with a FakeAgent; extend the FakeAgent with rollback_turn/delete_thread.

- file: tests/test_netbox_integration.py
  why: constructor patterns the new kwarg must not disturb.

- url: https://langchain-ai.github.io/langgraph/concepts/persistence/
  section: Checkpointer libraries; thread_id; update_state and RemoveMessage
  critical: aupdate_state(config, values, as_node=...) writes a new checkpoint; RemoveMessage(id) in a channel reduced by add_messages deletes that message.

- url: https://pypi.org/project/langgraph-checkpoint-sqlite/3.1.1/
  section: AsyncSqliteSaver.from_conn_string (async context manager), setup(), adelete_thread()
  critical: from_conn_string is an @asynccontextmanager yielding the saver; the connection closes on exit, so it must wrap the whole lifespan.

- file: PRPs/netbox-web-chat.md
  why: shape, gates and anti-patterns this PRP extends; "Future enhancements" item 1 is this feature.

- file: docs/development/2026-09-28_web-chat.md
  why: lists "No durable checkpointer" under Not done; append the outcome there or in a new dated note.
```

### Current Codebase tree (relevant parts)
```bash
src/agents/netbox_agent.py      # InMemorySaver() in __init__; checkpointer passed to create_deep_agent
src/web/{api,session,config,models,events,tracing}.py
frontend/composables/{useChatSocket,useConversations}.ts ; frontend/pages/index.vue
tests/test_web_{api,session,events,tracing}.py ; tests/test_netbox_integration.py
scripts/ws_smoke.py
conversation_history/  large_tool_results/   # middleware artifacts, keyed by thread_id, gitignored
```

### Desired Codebase tree (files to add / modify)
```bash
pyproject.toml                         # MODIFY: web extra += langgraph-checkpoint-sqlite==3.1.1
.env.example                           # MODIFY: WEB_CHECKPOINT_DB=data/web_checkpoints.sqlite
.gitignore                             # already ignores *.sqlite3 and *.db; ADD data/*.sqlite
src/agents/netbox_agent.py             # MODIFY: checkpointer kwarg (default InMemorySaver), rollback_turn(), delete_thread(), thread_exists()
src/web/config.py                      # MODIFY: WebConfig.checkpoint_db
src/web/checkpoints.py                 # NEW: open_checkpointer() async context manager around AsyncSqliteSaver
src/web/api.py                         # MODIFY: lifespan wraps saver; resumed carries conversation_id; DELETE /conversations/{id}
src/web/session.py                     # MODIFY: rollback on user cancel and on agent error; new cancelled text
frontend/composables/useChatSocket.ts  # MODIFY: resumed -> check conversation_id matches activeThreadId
frontend/composables/useConversations.ts # MODIFY: deleteConversation also calls DELETE /conversations/{id}
frontend/pages/index.vue               # MODIFY: banner text (restart no longer loses memory)
tests/test_web_checkpoints.py          # NEW: SQLite round-trip, reload across saver instances, unwritable path
tests/test_web_session.py              # MODIFY: cancel -> rollback_turn called with the pre-turn ids; error -> rollback
tests/test_web_api.py                  # MODIFY: resumed has conversation_id; DELETE route; FakeAgent gains rollback_turn/delete_thread
tests/test_netbox_integration.py       # MODIFY (append): checkpointer kwarg is forwarded; default is InMemorySaver
scripts/ws_smoke.py                    # MODIFY: --expect-known flag for the restart test
docs/setup/web-chat.md                 # MODIFY: Known limits "Memory is per process" -> durable; backup note
docs/development/2026-10-05_web-chat-persistence.md  # NEW decision note + README index line
```

### Known Gotchas of our codebase & Library Quirks
```python
# CRITICAL: the saver's connection lives only inside `async with AsyncSqliteSaver.from_conn_string(path)`.
# Wrap the ENTIRE lifespan body in it. Opening it, building the agent, then leaving the block
# closes the connection and every later aget_state raises.

# CRITICAL: pass the saver by object. create_deep_agent(checkpointer=saver) accepts any
# BaseCheckpointSaver (deepagents/graph.py:283). Do not call create_deep_agent twice per request.

# CRITICAL: default stays InMemorySaver(). 20 callers construct the agent without a checkpointer;
# the eval harness and session harness depend on fresh in-memory state per process.

# CRITICAL: await saver.setup() once before first use (creates the `checkpoints` and `writes` tables).

# GOTCHA: a cancelled run leaves state.next pending AND the orphaned messages checkpointed. The
# next user message does NOT resume the pending node (fresh input => fresh run) but the orphans
# stay. Rollback = aupdate_state(cfg, {"messages": [RemoveMessage(id=i) for i in orphan_ids]},
# as_node="model"). Verified: next becomes () and a following turn runs normally.
# "model" is the real node name in this graph (langchain/agents/factory.py:1502).

# GOTCHA: capture the message ids BEFORE the turn starts (aget_state -> values["messages"]), not
# after; the orphan set is "every id now present that was not present then". A turn that is
# cancelled before its first checkpoint has nothing to roll back; the helper must be a no-op then.

# GOTCHA: HumanMessage ids. The web path sends {"role": "user", "content": ...}; add_messages
# assigns a uuid4 id on insertion, so ids are stable in state but NOT known to the sender. Rollback
# therefore works by set difference, not by remembering the id we sent.

# GOTCHA: rollback must run AFTER the cancelled task has fully stopped (the lock is still held by
# the cancelled TurnRunner.run; do the rollback inside its except/finally before releasing).
# aupdate_state on a thread while a run writes to it would interleave checkpoints.

# GOTCHA: aget_state on an unknown thread returns a StateSnapshot with values == {} and
# config.configurable.checkpoint_id None - that is "unknown", not an exception. get_history()
# already handles this (returns []).

# GOTCHA: SQLite file path. Use an absolute path resolved from PROJECT_ROOT so `python -m src.web`
# started from another cwd does not create a second empty database. mkdir(parents=True).

# GOTCHA: WAL + one connection. AsyncSqliteSaver serialises through its own asyncio.Lock; the
# TurnRunner lock already serialises turns. Resume/history reads run concurrently with a turn and
# are fine (reads), but do not add a second process pointing at the same file.

# GOTCHA: conversations created before this change exist only in the browser. resume -> known:false
# is correct for them; the banner text should say "created before persistence or database
# removed", not "backend restarted".

# GOTCHA: frontend `resumed` races. setActiveThread(A) then setActiveThread(B) quickly: A's reply
# can arrive after B was selected. Include conversation_id in the chunk and drop mismatches.

# GOTCHA (unchanged from the web-chat PRP): the eval harness must not see any of this. Only
# src/web/ constructs a SQLite saver.
```

## Implementation Blueprint

### Architecture
```
FastAPI lifespan
  async with AsyncSqliteSaver.from_conn_string(<abs path>) as saver:
      await saver.setup()
      agent = await create_netbox_agent(..., checkpointer=saver)   # web only
      runner = TurnRunner(agent, cfg, trace_linker)
      yield
      await agent.cleanup()
                                            CLI / eval: create_netbox_agent(...)  -> InMemorySaver() as before

TurnRunner.run(turn):
  before = {m.id for m in state(thread).messages}
  try:   stream_events(...)                 -> normal path, checkpoints land in SQLite per step
  except CancelledError (user):             -> agent.rollback_turn(thread, keep=before); send cancelled
  except Exception:                         -> agent.rollback_turn(thread, keep=before); send error
```

### Data models and structure
```python
# src/web/config.py
class WebConfig(BaseModel):
    ...
    checkpoint_db: str = Field(default="data/web_checkpoints.sqlite")   # relative to PROJECT_ROOT

# src/web/models.py
class StreamChunk ...  # unchanged; "resumed" metadata gains "conversation_id": str
# ClientMessage unchanged; conversation deletion is an HTTP route (Task 7)
```

### Ordered task list
```yaml
Task 1: Dependency + config
MODIFY pyproject.toml: web extra += "langgraph-checkpoint-sqlite==3.1.1"
RUN ./venv/bin/pip install -e ".[web,dev]"   # adds aiosqlite, sqlite-vec, the saver; upgrades nothing (dry-run verified)
MODIFY .env.example: WEB_CHECKPOINT_DB=data/web_checkpoints.sqlite  (comment: absolute or PROJECT_ROOT-relative; back up with conversation_history/ and large_tool_results/)
MODIFY .gitignore: add `data/*.sqlite*`
MODIFY src/web/config.py: WebConfig.checkpoint_db from WEB_CHECKPOINT_DB

Task 2: Agent accepts a checkpointer (default unchanged)
MODIFY src/agents/netbox_agent.py:
  - __init__(..., checkpointer: BaseCheckpointSaver | None = None); self.checkpointer = checkpointer if checkpointer is not None else InMemorySaver()
  - create_netbox_agent(..., checkpointer=None) forwards it
  - ADD async def thread_exists(thread_id) -> bool: state = await self.agent.aget_state(cfg); return bool(state.values)
  - ADD async def message_ids(thread_id) -> set[str]
  - ADD async def rollback_turn(thread_id, keep_ids: set[str]) -> int:
        state = await self.agent.aget_state(cfg); orphans = [m.id for m in state.values.get("messages", []) if m.id not in keep_ids]
        if orphans: await self.agent.aupdate_state(cfg, {"messages": [RemoveMessage(id=i) for i in orphans]}, as_node="model")
        return len(orphans)
  - ADD async def delete_thread(thread_id): await self.checkpointer.adelete_thread(thread_id) (InMemorySaver has it too)
  - DO NOT touch query(), stream_events(), get_history(), the prompt, middleware or skills

Task 3: Saver lifecycle
CREATE src/web/checkpoints.py:
  @asynccontextmanager async def open_checkpointer(path: str) -> AsyncIterator[AsyncSqliteSaver]:
      p = Path(path); p = p if p.is_absolute() else PROJECT_ROOT / p; p.parent.mkdir(parents=True, exist_ok=True)
      async with AsyncSqliteSaver.from_conn_string(str(p)) as saver:
          await saver.setup(); logger.info("Checkpoint store open", path=str(p)); yield saver
  (PROJECT_ROOT imported from src.agents.netbox_agent)
MODIFY src/web/api.py lifespan:
  async with open_checkpointer(web_config.checkpoint_db) as saver:
      agent = await _build_agent(web_config, netbox_config, checkpointer=saver)
      ... existing probe / tracing / TurnRunner ...; app.state.checkpointer = saver
      try: yield
      finally: await agent.cleanup()
  _build_agent(web_config, netbox_config, checkpointer=None) forwards the kwarg (tests patch _build_agent, so signature change is test-visible)
  Any OSError/sqlite3 error from open_checkpointer propagates => uvicorn exits non-zero. Log the path first.

Task 4: Restart smoke
MODIFY scripts/ws_smoke.py: --expect-known {true,false} asserts the resumed metadata; exit 3 on mismatch
RUN the Gate 3 restart sequence (below) before writing any rollback code; it proves Tasks 1-3 alone.

Task 5: Cancel and error rollback
MODIFY src/web/session.py TurnRunner.run:
  - before stream: keep_ids = await self.agent.message_ids(conversation_id)  (FakeAgent in tests returns set())
  - user-cancel branch: removed = await self.agent.rollback_turn(conversation_id, keep_ids); content = "Cancelled. The thread was rolled back to your previous question." ; metadata["rolled_back_messages"] = removed
  - agent-error branch: same rollback before sending the error chunk (a failed turn must not leave a half-turn either)
  - rollback runs INSIDE the except blocks (lock still held), wrapped in try/except so a rollback failure logs and does not mask the original outcome
MODIFY tests/test_web_session.py: FakeAgent gets message_ids()/rollback_turn() recorders; assert rollback called with the pre-turn ids on cancel and on error, not on done

Task 6: Frontend cancel wording
MODIFY frontend/composables/useChatSocket.ts 'cancelled' handler: override text "(cancelled — rolled back)"; keep partial text visible, mark meta.cancelled
MODIFY frontend/pages/index.vue banner: "The backend has no memory of this conversation (it predates persistent storage or the database was removed). The transcript below is only in your browser."

Task 7: Resume hardening + server-side delete
MODIFY src/web/api.py:
  - resume: known = await agent.thread_exists(cid); turns via get_history as now; metadata += {"conversation_id": cid}
  - ADD @app.delete("/conversations/{conversation_id}") -> agent.delete_thread; also runner._ledger.pop(cid, None); 204
MODIFY frontend/composables/useChatSocket.ts 'resumed': if (m.conversation_id && m.conversation_id !== activeThreadId.value) break
MODIFY frontend/composables/useConversations.ts deleteConversation: fire-and-forget $fetch DELETE; local delete proceeds regardless
MODIFY tests/test_web_api.py: resumed carries conversation_id; DELETE returns 204 and FakeAgent.delete_thread called

Task 8: Tests for the saver itself
CREATE tests/test_web_checkpoints.py (uses a tmp_path SQLite file, a 2-node StateGraph, NO agent):
  - write with one saver, reload with a second instance over the same file, values equal, next == ()
  - private PrivateStateAttr field round-trips
  - open_checkpointer on a path under a read-only dir raises (not swallowed)
  - rollback recipe: cancel mid-run, RemoveMessage via aupdate_state as_node, next cleared, next invoke normal
tests/test_netbox_integration.py: append test that NetBoxDeepAgent(checkpointer=sentinel).checkpointer is sentinel and default is InMemorySaver

Task 9: Docs
MODIFY docs/setup/web-chat.md: Known limits -> "Memory survives restarts (SQLite at WEB_CHECKPOINT_DB). Conversations from before 2026-10 are browser-only." Backup = the .sqlite file + conversation_history/ + large_tool_results/. Troubleshooting row for a locked/unwritable DB.
CREATE docs/development/2026-10-05_web-chat-persistence.md + README index line: decisions (saver injection with in-memory default; rollback by RemoveMessage; no transcript import; why no catalogue DB), the verified facts above, Gate results.
MODIFY docs/development/2026-09-28_web-chat.md "Not done": strike the durable-checkpointer line with a pointer.
```

### Per-task pseudocode

```python
# Task 2 - src/agents/netbox_agent.py (additions only)
from langchain_core.messages import RemoveMessage
from langgraph.checkpoint.base import BaseCheckpointSaver

def __init__(self, ..., checkpointer: BaseCheckpointSaver | None = None):
    ...
    # Web path injects a durable saver; everything else keeps per-process memory.
    self.checkpointer = checkpointer if checkpointer is not None else InMemorySaver()

async def message_ids(self, thread_id: str) -> set[str]:
    state = await self.agent.aget_state({"configurable": {"thread_id": thread_id}})
    return {m.id for m in (state.values.get("messages", []) if state and state.values else []) if m.id}

async def rollback_turn(self, thread_id: str, keep_ids: set[str]) -> int:
    """Remove every message added since `keep_ids` and clear any pending node."""
    cfg = {"configurable": {"thread_id": thread_id}}
    state = await self.agent.aget_state(cfg)
    msgs = state.values.get("messages", []) if state and state.values else []
    orphans = [m.id for m in msgs if m.id and m.id not in keep_ids]
    if not orphans:
        return 0
    # as_node="model": the write is attributed to the model node, which clears the pending
    # "tools"/"model" task left by a cancelled run (verified on langgraph 1.2.5).
    await self.agent.aupdate_state(cfg, {"messages": [RemoveMessage(id=i) for i in orphans]}, as_node="model")
    logger.info("Rolled back turn", thread_id=thread_id[:8], removed=len(orphans))
    return len(orphans)
```

```python
# Task 3 - src/web/api.py lifespan (shape)
async with open_checkpointer(web_config.checkpoint_db) as saver:
    agent = await _build_agent(web_config, netbox_config, checkpointer=saver)
    app.state.agent = agent
    app.state.checkpointer = saver
    trace_linker = await asyncio.to_thread(resolve_trace_linker)
    app.state.runner = TurnRunner(agent, web_config, trace_linker=trace_linker)
    try:
        yield
    finally:
        await agent.cleanup()
# leaving the `async with` closes the aiosqlite connection after the agent is gone
```

```python
# Task 5 - src/web/session.py (inside run(), after acquiring the lock)
keep_ids = await self.agent.message_ids(conversation_id)
try:
    async for mode, payload in self.agent.stream_events(text, conversation_id, run_id=run_id): ...
    await send(finish(...))
except asyncio.CancelledError:
    if not self._user_cancel: raise
    removed = await self._safe_rollback(conversation_id, keep_ids)
    await send(StreamChunk(type="cancelled", completed=True,
        content="Cancelled. The thread was rolled back to your previous question.",
        metadata={**self._terminal_meta(stats, conversation_id), "rolled_back_messages": removed}))
except Exception as e:
    removed = await self._safe_rollback(conversation_id, keep_ids)
    ... existing error chunk, metadata += rolled_back_messages

async def _safe_rollback(self, cid, keep_ids) -> int:
    try: return await self.agent.rollback_turn(cid, keep_ids)
    except Exception as e: logger.error("Rollback failed", error=str(e)); return -1
```

### Integration Points
```yaml
CONFIG (.env):
  WEB_CHECKPOINT_DB=data/web_checkpoints.sqlite    # PROJECT_ROOT-relative unless absolute
DEPENDENCIES (web extra):
  langgraph-checkpoint-sqlite==3.1.1  (+ aiosqlite, sqlite-vec)
ROUTES:
  DELETE /conversations/{id}   -> 204; deletes checkpoints + ledger entry
WS PROTOCOL:
  resumed.metadata += conversation_id ; cancelled.metadata += rolled_back_messages
FILES ON DISK (back up together):
  data/web_checkpoints.sqlite, conversation_history/, large_tool_results/
UNCHANGED SURFACES:
  python -m src.main, tests/eval/*, NetBoxDeepAgent.query(), NETBOX_SYSTEM_PROMPT, middleware, skills
```

## Validation Loop

### Gate 1 - syntax / style / types
```bash
cd /home/ola/dev/netboxdev/ollamaDeepAgents
./venv/bin/pip install -e ".[web,dev]"
./venv/bin/pip list | grep -E "langgraph-checkpoint|aiosqlite"     # checkpoint still 4.1.1; sqlite saver 3.1.1
./venv/bin/ruff check src/web src/agents/netbox_agent.py tests/test_web_*.py scripts/ws_smoke.py --fix
./venv/bin/mypy src/web
cd frontend && npm run build
```

### Gate 2 - unit tests (no llama-server, no NetBox)
```bash
./venv/bin/python -m pytest tests/test_web_checkpoints.py tests/test_web_session.py tests/test_web_api.py tests/test_web_events.py -q
./venv/bin/python -m pytest tests/test_netbox_integration.py -q    # same 7 pre-existing failures as master, no new ones
```

### Gate 3 - restart and cancel against the real stack
```bash
# backend up with the default WEB_CHECKPOINT_DB; llama-server and NetBox up
CID=$(python3 -c 'import uuid;print(uuid.uuid4().hex)')
./venv/bin/python scripts/ws_smoke.py "Give me the name and id of exactly one site belonging to tenant Dunder-Mifflin. Reply with only 'name (id)'." --conversation-id $CID --expect-known false
# restart: kill the backend process, start `./venv/bin/python -m src.web` again, wait for /health
./venv/bin/python scripts/ws_smoke.py "Without calling any tools, repeat the site name and id from your previous answer." --conversation-id $CID --expect-known true
#   Expected: resumed known=true turns=1; answer repeats "DM-Akron (2)" (or whatever turn 1 said); tools=0.
ls -la data/web_checkpoints.sqlite ; sqlite3 data/web_checkpoints.sqlite 'select count(*) from checkpoints where thread_id=?' -- "$CID" 2>/dev/null || true

# cancel rollback
./venv/bin/python scripts/ws_smoke.py "List every device at every Dunder-Mifflin site with role and rack position." --conversation-id <cid> --cancel-after 25
curl -s 127.0.0.1:8010/conversations/<cid>/messages    # Expected: [] (no orphaned user message) or only completed turns
#   then one more turn on that thread: context_end ~= 8.7k + question, not inflated by the cancelled tool results

# unwritable path fails loudly
WEB_CHECKPOINT_DB=/proc/nope.sqlite ./venv/bin/python -m src.web ; echo "exit=$?"   # non-zero, log names the path
```

### Gate 4 - browser
```bash
# 1. Chat, restart backend, reload page: no "memory lost" banner; follow-up answered from memory.
# 2. Stop a long turn: bubble shows "(cancelled — rolled back)"; next question unaffected (tool panel shows a fresh lookup only if the question needs one).
# 3. Delete a conversation in the sidebar: GET /conversations/{id}/messages -> 404 afterwards.
# 4. Rapidly switch A -> B: B's header never shows A's known/turns values (resumed id check).
```

### Gate 5 - comparability
```bash
git diff master -- src/agents/netbox_agent.py | grep -c "^-" # only additive hunks except the one-line default change
./venv/bin/python -m src.main --batch "What sites do I have?"   # CLI still runs on InMemorySaver (no data/*.sqlite growth)
```

## Final validation Checklist
- [ ] Gates 1-5 pass; outputs recorded in `docs/development/2026-10-05_web-chat-persistence.md`
- [ ] `grep -n "InMemorySaver()" src/agents/netbox_agent.py` still shows the default
- [ ] No `data/*.sqlite` created by the CLI or the eval harness
- [ ] Cancel leaves `GET /conversations/{id}/messages` with completed turns only
- [ ] `resumed` carries `conversation_id`; frontend ignores mismatches
- [ ] `.env.example` documents `WEB_CHECKPOINT_DB`; run book documents backup set

---

## Anti-Patterns to Avoid
- ❌ Don't make SQLite the default checkpointer for `NetBoxDeepAgent` - the eval harness needs fresh memory per process.
- ❌ Don't fall back to `InMemorySaver` when the database cannot open; fail startup.
- ❌ Don't open the saver with `from_conn_string` and leave the `async with` before the agent is done.
- ❌ Don't roll back by re-sending the browser transcript; use `RemoveMessage` on the server state.
- ❌ Don't roll back from outside the cancelled `TurnRunner.run` while it may still be writing.
- ❌ Don't add a transcript/title/ledger database; the browser remains the transcript cache.
- ❌ Don't import browser transcripts into threads (2,000-char tool previews = claims without evidence).
- ❌ Don't upgrade `langgraph`/`langgraph-checkpoint`/`deepagents` as part of this change; pin the saver to 3.1.1.
- ❌ Don't point two processes at the same SQLite file.

## Out of scope (explicit)
Transcript import for pre-persistence conversations; server-side conversation catalogue, titles, turn table or usage persistence; multi-user ownership; PostgreSQL; llama.cpp slot-cache save/restore; vector or archive retrieval; changes to summarization policy or context budgets; resuming (rather than discarding) an interrupted tool loop.

## Future enhancements
1. Ledger persistence: write `TurnUsage` rows into the same SQLite file (separate table) so the token ledger survives restarts too.
2. Persist `WEB_CHECKPOINT_DB` snapshots alongside `docs/traces/` for sessions worth keeping.
3. Forced-compaction + restart test as a standing integration test once a compaction has been observed on this model.
4. A `Command(resume=...)` path to continue an interrupted tool loop instead of discarding it, if the UI ever wants "resume where I stopped".

## Confidence: 9/10
High because every moving part was executed, not assumed, on the installed versions: the SQLite
saver installs into `./venv` without upgrades and round-trips a private state field across saver
instances; the cancel failure (orphaned messages, pending `next`) was reproduced against the real
agent; the `RemoveMessage`-via-`aupdate_state` rollback was shown to clear both and leave a thread
that runs normally; A -> B -> A within one process was shown to work, so the fix targets the real
fault. The -1: `as_node="model"` for the rollback write was verified on a toy graph with the same
node names, not yet on the DeepAgents graph with its middleware hook nodes - Task 5's test on the
real agent (Gate 3) is where that assumption is checked, and the fallback is `as_node` set to the
last node in `state.next` or omitted.
