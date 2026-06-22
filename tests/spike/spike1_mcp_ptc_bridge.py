"""Spike 1 — Verify MCP-derived BaseTools auto-bridge into PTC.

Resolves §7.1 of `docs/development/2026-06-03_quickjs-code-interpreter-research.md`:
do `langchain-mcp-adapters` BaseTools, when passed to `CodeInterpreterMiddleware.ptc=[...]`,
become callable inside JS as `tools.<sanitizedName>(...)` — and actually round-trip
to the real NetBox MCP server?

Approach: build a full agent (deepseek-v4-flash:cloud) with `CodeInterpreterMiddleware`
allowlisting all 4 NetBox MCP tools. Ask the model a *trivial* JS request: "use eval
to make exactly one tools.<name>() call with a known-good filter." Inspect the
resulting trace for:
  - Whether the model emitted an `eval` tool call
  - Whether the JS inside it successfully called the bridged tool
  - Whether the returned value carried real NetBox data

This is degenerate JS (one wrapped tool call), so any model-fluency issues that
might arise on full multi-step JS workflows are minimised here — we're isolating
the bridge mechanism, not testing JS authoring quality (that's Spike 3).
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

_PROMPT = """You are testing a sandbox bridge. Execute exactly this JavaScript inside the eval tool — no other tool calls, no planning, just one eval invocation:

```javascript
const result = await tools.netboxGetObjects({
  object_type: "dcim.site",
  filters: { name: "DM-Akron" },
  fields: ["id", "name", "slug", "status"],
  limit: 5,
});
JSON.stringify(result);
```

Then report what `result` contained. Nothing else."""


async def main() -> None:
    load_dotenv()

    cfg = load_netbox_config()
    mcp = await create_netbox_mcp_client(cfg.url, cfg.token, cfg.mcp_server_path)
    wrapper = NetBoxToolWrapper(mcp)
    tools = await wrapper.get_tools()
    print(f"[setup] {len(tools)} MCP tools: {[t.name for t in tools]}")

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
        system_prompt=(
            "You are a sandbox-bridge test agent. Follow the user's instructions "
            "literally — make exactly the tool call requested, no more, no less."
        ),
        middleware=[code_interp],
        backend=FilesystemBackend(root_dir=str(PROJECT_ROOT), virtual_mode=True),
        checkpointer=InMemorySaver(),
    )
    print("[setup] agent built. middleware tool surface includes `eval`.")

    print("\n[run] Asking model to call eval with trivial JS…")
    state = await agent.ainvoke(
        {"messages": [{"role": "user", "content": _PROMPT}]},
        config={"configurable": {"thread_id": "spike1"}},
    )

    messages = state.get("messages", [])
    print(f"\n[result] {len(messages)} messages in final state.\n")
    for i, m in enumerate(messages):
        mtype = getattr(m, "type", "?")
        if mtype == "ai":
            calls = getattr(m, "tool_calls", None) or []
            content = (getattr(m, "content", "") or "")
            if calls:
                for tc in calls:
                    args_str = str(tc.get("args", {}))[:400]
                    print(f"  [{i}] AI → tool_call name={tc.get('name')!r} args={args_str}")
            elif content:
                print(f"  [{i}] AI → final: {content[:600]}")
        elif mtype == "tool":
            name = getattr(m, "name", "?")
            body = (getattr(m, "content", "") or "")
            print(f"  [{i}] TOOL[{name}] result (first 500 chars): {str(body)[:500]}")
        elif mtype == "human":
            content = getattr(m, "content", "")
            print(f"  [{i}] HUMAN → {str(content)[:120]}")


if __name__ == "__main__":
    asyncio.run(main())
