# 2026-10-05: Web Chat Persistence — SQLite checkpoints and cancel rollback

**Status:** implemented on branch `feature/web-chat-persistence` from
`PRPs/netbox-web-chat-persistence.md` (brief: `PRPs/initials/netbox-web-chat-persistence.md`).
Run book: `docs/setup/web-chat.md`. Follows the assessment of an external persistence report
(2026-10-05); steps 1-4 of that assessment are implemented here, the rest declined (below).

## What was built

- `NetBoxDeepAgent(checkpointer=...)` / `create_netbox_agent(checkpointer=...)`. Default stays
  `InMemorySaver()`, so `python -m src.main`, `tests/eval/*` and all 20 existing callers are
  unchanged. New helpers: `thread_exists()`, `message_ids()`, `rollback_turn()`, `delete_thread()`.
- `src/web/checkpoints.py` — `open_checkpointer(path)` wraps `AsyncSqliteSaver.from_conn_string`
  + `setup()` for the whole FastAPI lifespan; relative paths resolve from `PROJECT_ROOT`;
  an unopenable path aborts startup (no fallback to memory). Config: `WEB_CHECKPOINT_DB`
  (default `data/web_checkpoints.sqlite`, gitignored).
- `TurnRunner` snapshots the thread's message ids before each turn and, on user cancel or agent
  error, calls `rollback_turn()` while it still holds the turn lock. The cancelled chunk reports
  `rolled_back_messages` and reads "rolled back to your previous question".
- `resumed` carries `conversation_id` (frontend drops late replies for other threads);
  `DELETE /conversations/{id}` forgets a thread (checkpoints + ledger; 409 while its turn runs);
  sidebar delete calls it fire-and-forget. Banner text now says "predates persistent storage".
- Dependency: `langgraph-checkpoint-sqlite==3.1.1` in the `web` extra. `pip` added only
  `aiosqlite 0.22.1` and `sqlite-vec 0.1.9`; `langgraph-checkpoint` stayed at 4.1.1.

## Decisions

1. **Checkpointer injection with an in-memory default.** The eval harness depends on fresh
   per-process memory; only `src/web/` ever constructs a durable saver.
2. **Fail startup rather than fall back.** A web server that cannot persist memory while the
   browser shows transcripts would reintroduce the exact failure this fixes, silently.
3. **Rollback, not resume, for cancelled turns.** Measured before the change (2026-10-05):
   cancelling after the first tool result left the thread as `[user]` with no answer and
   `state.next` pointing at the unfinished node; the next message started a fresh run (LangGraph
   treats non-None input as new input, `pregel/_loop.py:_first`) but the orphan stayed in every
   later prompt. `RemoveMessage` via `aupdate_state` deletes it and clears the pending task.
4. **The rollback is attributed to the node that routes to END, discovered from the graph.**
   The PRP assumed `as_node="model"`. Unit tests showed `aupdate_state` schedules the successors
   of `as_node`, so writing as `model` left `next == ('tools',)`. In the real DeepAgents graph the
   only edge to `__end__` leaves `FilterErrorRecoveryMiddleware.after_model` (conditional), not
   `model`; `_rollback_node()` reads `agent.get_graph().edges` once and falls back to `model`.
   This was the PRP's stated -1 and it was real.
5. **No transcript import, no catalogue database.** Browser transcripts hold 2,000-char tool
   previews; importing them would create threads with claims and no evidence, the contamination
   shape the session harness documented. The browser remains the transcript cache; the token
   ledger stays in memory (its numbers also live in the browser and LangSmith).
6. **Artifacts need no change.** The summarizer's `conversation_history/<thread>.md` and
   `large_tool_results/` are keyed by thread id under `PROJECT_ROOT` and already survive restarts;
   the run book says to back them up with the database.

## Verified facts (installed versions, not docs)

- `./venv` runs deepagents 0.7.5, langgraph 1.2.5, langgraph-checkpoint 4.1.1 (`uv.lock` says
  0.7.14 / 1.2.11 / 4.2.0 and was never installed).
- SQLite saver round-trip: a graph with a `PrivateStateAttr` field (like
  `_summarization_event`) written by one saver instance reloads identically from a second
  instance over the same file; `aget_state` of an unknown thread is `values == {}`.
- A -> B -> A within one process already kept A's memory; the fault was restart-only.

## Gate results (2026-10-05)

Gate 1: ruff clean on all changed files (the pre-existing 8 `E402` in `netbox_agent.py` remain);
`mypy src/web` clean; `npm run build` passes.
Gate 2: 48 web tests pass (`test_web_checkpoints` 6 new, `test_web_session` +3,
`test_web_api` +1); `test_netbox_integration.py` shows the same 7 pre-existing failures as master.

Gate 3, real stack:

| Check | Result |
|---|---|
| Turn 1 on a fresh thread ("one Dunder-Mifflin site, name (id)") | `resumed known=false`; answer **DM-Akron (2)**, 4 model calls, 3 tools, 66.8 s; `data/web_checkpoints.sqlite` created |
| **Backend killed and restarted**, same thread | `GET /conversations/{id}/messages` returned the 2 messages; `resumed known=true turns=1`; follow-up "repeat the site name and id without tools" answered **DM-Akron (2)** with **0 tools, 1 model call, 5.0 s**; 41 checkpoints stored for the thread |
| Unwritable `WEB_CHECKPOINT_DB` (`/proc/nope/...`) | process exits 3 with `No such file or directory: '/proc/nope'`; nothing listening |
| Cancel after the first tool result, then a new message (final, two-pass rollback) | `cancelled` chunk with `rolled_back_messages=3`; `GET /conversations/{id}/messages` -> 404 (empty); `resumed known=true turns=0`; next turn "Say OK": 1 model call, 0 tools, 3 s, **context 8,738** (the fresh-thread baseline); LangSmith shows that call's input as `[system, human]` only. Two earlier attempts left a 7,439-char tool message in the input (context 11,060) - see the defect section below |

## Defect found by Gate 3, fixed before merge: pending writes of parallel tool calls

The first real cancel test looked clean (`GET /conversations/{id}/messages` was empty, the next
turn ran) but LangSmith showed the next model call's input was `[system, tool (7,439 chars),
human]`: a tool result from the cancelled turn had survived. `get_history()` hides tool
messages, so the transcript view could not show it. Mechanism, reproduced with a Send-based
toy graph on both savers:

- The cancelled model call issued **two tool calls**; langchain's ToolNode runs each as its own
  task. `read_file` finished in 10 ms, `netbox_get_objects` was cancelled. The finished tool's
  result existed only as a **pending write** on the step, not in the committed `messages`
  channel.
- `aget_state(cfg)` merges pending writes into `values`, so the naive orphan list included the
  pending id; `RemoveMessage` acts on the committed channel and that id was not there. On the
  toy graph this raises *"Attempting to delete a message with an ID that doesn't exist"*; on the
  real agent it passed silently and the pending write was carried into the next turn.
- First fix attempt: compute orphans from the state **pinned to the checkpoint id** (committed
  only) and remove just those. On the toy graph `aupdate_state` dropped the pending write; on
  the real agent it did the opposite — `aupdate_state` applies the pending writes of tasks that
  had already finished *into the new checkpoint* (`pregel/main.py`, "apply writes from tasks that
  already ran"), so the finished `read_file` result became committed by the rollback itself
  (checkpoint `src=update` held exactly that one ToolMessage). The post-rollback safety check
  logged `Rollback incomplete leftover=1`, which is how this was caught.
- Final fix: **two passes.** Pass 1 removes the committed orphans (and, as a side effect,
  commits any finished-but-uncommitted tool results and clears the pending step); pass 2
  re-reads the state and removes everything not in the pre-turn id set. A warning is logged if
  anything survives both passes. Regression test with parallel `Send` tool tasks:
  `tests/test_web_checkpoints.py::test_rollback_drops_pending_parallel_tool_result`.

## Not done / follow-ups

- Ledger persistence (a `TurnUsage` table in the same SQLite file).
- Forced-compaction + restart as a standing test, once compaction has been observed on this model.
- `Command(resume=...)` to continue an interrupted tool loop instead of discarding it.
