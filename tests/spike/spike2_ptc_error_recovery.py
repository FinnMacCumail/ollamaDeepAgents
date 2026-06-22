"""Spike 2 — Verify error recovery inside `eval`.

Resolves §7.2 of `docs/development/2026-06-03_quickjs-code-interpreter-research.md`:
when a PTC-invoked tool fails (e.g. NetBox returns 400 for an invalid filter),
what does the model see? Can it recover?

The existing `FilterErrorRecoveryMiddleware` (`src/middleware/filter_recovery.py`)
catches ValueError + ToolException from direct tool calls and converts them to
structured `TOOL_VALIDATION_ERROR` / `TOOL_API_ERROR` ToolMessages. Per the
LangChain interpreter docs, "PTC calls currently execute through the interpreter
bridge and do not go through the normal tool calling path" — so that middleware
almost certainly does NOT see PTC failures.

We need to verify:
  (a) what an uncaught PTC tool error looks like from the model's perspective
  (b) whether `try/catch` inside JS lets the model see a useful error string
  (c) whether the model can issue a corrective follow-up `eval` call

The deliberate bad call: an invalid filter pattern that NetBox returns 400 for.
We'll use `assigned_object_id__lol` (nonsense suffix) which the local validator
rejects with ValueError → ToolException.

Two test runs:
  Test A — naked PTC call (no try/catch). What surfaces?
  Test B — wrapped in try/catch. Does the model see a useful exception?
"""

from __future__ import annotations

import asyncio

from dotenv import load_dotenv
from langchain_quickjs import CodeInterpreterMiddleware

from src.agents.ollama_config import create_ollama_model
from src.tools.netbox_tools import NetBoxToolWrapper, create_netbox_mcp_client
from src.utils.config import load_netbox_config

from deepagents import create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend
from langgraph.checkpoint.memory import InMemorySaver
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


_PROMPT_NAKED = """Execute exactly this JavaScript via the eval tool — no try/catch, no other tool calls:

```javascript
const result = await tools.netboxGetObjects({
  object_type: "ipam.ipaddress",
  filters: { assigned_object_id__lol: 5 },
  fields: ["id", "address"],
  limit: 1,
});
JSON.stringify(result);
```

After the eval call returns (or fails), describe in 1-2 sentences what you received. Do not make a second eval call."""

_PROMPT_TRYCATCH = """Execute exactly this JavaScript via the eval tool:

```javascript
let outcome;
try {
  const result = await tools.netboxGetObjects({
    object_type: "ipam.ipaddress",
    filters: { assigned_object_id__lol: 5 },
    fields: ["id", "address"],
    limit: 1,
  });
  outcome = { ok: true, data: result };
} catch (e) {
  outcome = { ok: false, error_message: String(e.message || e), error_name: e.name };
}
JSON.stringify(outcome);
```

After the eval call returns, describe in 1-2 sentences what you received. Do not make a second eval call."""


async def run_test(label: str, prompt: str) -> None:
    print(f"\n{'='*60}")
    print(f"=== {label}")
    print(f"{'='*60}")
    load_dotenv()

    cfg = load_netbox_config()
    mcp = await create_netbox_mcp_client(cfg.url, cfg.token, cfg.mcp_server_path)
    wrapper = NetBoxToolWrapper(mcp)
    tools = await wrapper.get_tools()

    code_interp = CodeInterpreterMiddleware(
        ptc=tools,
        timeout=30.0,
        max_ptc_calls=64,
        max_result_chars=8000,
        capture_console=True,
        subagents=False,
    )

    model = create_ollama_model("deepseek-v4-flash:cloud", validate=False)
    agent = create_deep_agent(
        model=model,
        tools=tools,
        system_prompt="You are a sandbox-bridge test agent. Follow the user's instructions literally.",
        middleware=[code_interp],
        backend=FilesystemBackend(root_dir=str(PROJECT_ROOT), virtual_mode=True),
        checkpointer=InMemorySaver(),
    )

    state = await agent.ainvoke(
        {"messages": [{"role": "user", "content": prompt}]},
        config={"configurable": {"thread_id": f"spike2-{label}"}},
    )

    messages = state.get("messages", [])
    print(f"\n[{len(messages)} messages in final state]\n")
    for i, m in enumerate(messages):
        mtype = getattr(m, "type", "?")
        if mtype == "ai":
            calls = getattr(m, "tool_calls", None) or []
            content = (getattr(m, "content", "") or "")
            if calls:
                for tc in calls:
                    args_str = str(tc.get("args", {}))[:300]
                    print(f"  [{i}] AI tool_call name={tc.get('name')!r}\n      args={args_str}")
            elif content:
                print(f"  [{i}] AI final: {content[:800]}")
        elif mtype == "tool":
            name = getattr(m, "name", "?")
            body = (getattr(m, "content", "") or "")
            print(f"  [{i}] TOOL[{name}] (first 700 chars):\n      {str(body)[:700]}")
        elif mtype == "human":
            content = getattr(m, "content", "")
            print(f"  [{i}] HUMAN: {str(content)[:100]}…")


async def main() -> None:
    await run_test("TEST A — Naked PTC call (no try/catch)", _PROMPT_NAKED)
    await run_test("TEST B — Wrapped in try/catch", _PROMPT_TRYCATCH)


if __name__ == "__main__":
    asyncio.run(main())
