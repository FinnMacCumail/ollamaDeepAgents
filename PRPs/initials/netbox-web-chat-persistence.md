# FEATURE

Durable conversation memory for the NetBox web chat. Today `NetBoxDeepAgent` keeps LangGraph
state in an `InMemorySaver`, so every conversation the browser still shows becomes unknown to
the backend the moment `python -m src.web` restarts. The browser's "server memory lost" banner
is the only mitigation. Four changes:

1. **Inject a durable checkpointer.** `NetBoxDeepAgent` / `create_netbox_agent` take an optional
   `checkpointer`; the web server opens an `AsyncSqliteSaver` in its FastAPI lifespan and passes
   it in. The CLI and the eval harnesses keep `InMemorySaver` by default and are otherwise
   untouched.
2. **Resume survives a restart for free**, because `resume` already reads the checkpoint via
   `get_history()`. Tag the `resumed` reply with the conversation id so a slow reply can never
   land on a different selected thread.
3. **Cancel rolls the thread back to its last completed turn.** Measured: a cancelled turn leaves
   the user question and any partial AI/tool messages in the thread forever, plus a pending
   graph task. With persistence that orphan becomes permanent, so cancel must remove it.
4. **Artifacts are already durable** (`conversation_history/<thread>.md`, `large_tool_results/`
   under the project root, keyed by thread). Document that they must be backed up with the
   database and leave the filesystem backend alone.

Hard constraints: `query()`, `NETBOX_SYSTEM_PROMPT`, middleware and skills stay byte-identical
(eval comparability). No upgrade of `langgraph` / `langgraph-checkpoint` / `deepagents` in the
project venv. No server-side conversation catalogue, transcript tables, auth, or browser
transcript import — single-operator tool.

# USER VALUE

As the operator of the local NetBox assistant,
I want a conversation I return to after a backend restart to still be known to the model,
so that follow-ups keep working across restarts, and a turn I cancel does not leave a dangling
question in the model's memory.

# NOTES FOR WHOEVER RUNS generate-prp

- Follow the shape of `PRPs/netbox-web-chat.md`. Every claim about LangGraph/saver behaviour
  must be the one verified on 2026-10-05 against the installed `venv` (langgraph 1.2.5,
  langgraph-checkpoint 4.1.1, deepagents 0.7.5), not the `uv.lock` versions, which are newer and
  were never installed.
- Out of scope, explicitly: the ChatGPT report's catalogue/transcript tables, idempotency keys,
  ownership checks, browser-transcript import, slot-cache persistence, vector retrieval.
