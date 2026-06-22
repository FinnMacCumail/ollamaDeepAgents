"""Spike 3 — Measure VLAN 100 wall-time delta with vs. without PTC.

Resolves the load-bearing question from §7.3 and §6.6 of
`docs/development/2026-06-03_quickjs-code-interpreter-research.md`:
does CodeInterpreterMiddleware actually reduce wall time on a real multi-call
NetBox query, or is the projected "70s → 20-30s" speedup a marketing extrapolation?

Anthropic's own data on τ²-bench (1-2 sequential tool calls per turn) shows
PTC scores unchanged and costs 8% MORE. Our NetBox workload is the same shape
(4 tools, 5-10 sequential cycles with dependencies). The fresh research strongly
predicts this spike will show <30% improvement — possibly a regression.

Approach: run the VLAN 100 benchmark query twice on deepseek-v4-flash:cloud:
  A) Production agent (current state): system prompt + skill content + 4 NetBox
     tools as direct tool calls. No CodeInterpreterMiddleware.
  B) Same agent + CodeInterpreterMiddleware(ptc=[4 netbox tools]). The model
     now has BOTH direct tool calls AND eval available; it can choose.

The agent ainvoke happens once per variant on a fresh thread. We measure
wall time, tool-call count, and dump the tool sequence so we can see which
mechanism the model chose.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from langchain_quickjs import CodeInterpreterMiddleware

from deepagents import HarnessProfile, create_deep_agent, register_harness_profile
from deepagents.backends.filesystem import FilesystemBackend
from langgraph.checkpoint.memory import InMemorySaver

from src.agents.netbox_agent import NETBOX_SYSTEM_PROMPT
from src.agents.ollama_config import create_ollama_model
from src.middleware.filter_recovery import FilterErrorRecoveryMiddleware
from src.tools.netbox_tools import NetBoxToolWrapper, create_netbox_mcp_client
from src.utils.config import load_netbox_config

PROJECT_ROOT = Path(__file__).resolve().parents[2]

VLAN_QUERY = (
    "Show where VLAN 100 is deployed across Jimbob's Banking sites, "
    "including devices using this VLAN and IP allocations"
)


async def build_agent(*, with_ptc: bool):
    cfg = load_netbox_config()
    mcp = await create_netbox_mcp_client(cfg.url, cfg.token, cfg.mcp_server_path)
    wrapper = NetBoxToolWrapper(mcp)
    tools = await wrapper.get_tools()

    middleware = [FilterErrorRecoveryMiddleware()]
    if with_ptc:
        middleware.append(
            CodeInterpreterMiddleware(
                ptc=tools,
                timeout=30.0,
                max_ptc_calls=64,
                max_result_chars=8000,
                capture_console=True,
                subagents=False,
            )
        )

    model = create_ollama_model("deepseek-v4-flash:cloud", validate=False)

    agent = create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=NETBOX_SYSTEM_PROMPT,
        middleware=middleware,
        skills=["src/skills"],
        backend=FilesystemBackend(root_dir=str(PROJECT_ROOT), virtual_mode=True),
        checkpointer=InMemorySaver(),
    )
    return agent


def summarise(state: dict) -> dict:
    messages = state.get("messages", [])
    tool_calls_by_name: dict[str, int] = {}
    final_answer = ""
    for m in messages:
        if getattr(m, "type", None) == "ai":
            for tc in (getattr(m, "tool_calls", None) or []):
                n = tc.get("name", "?")
                tool_calls_by_name[n] = tool_calls_by_name.get(n, 0) + 1
            if getattr(m, "content", None) and not (getattr(m, "tool_calls", None) or []):
                final_answer = m.content
    return {
        "n_messages": len(messages),
        "tool_calls_by_name": tool_calls_by_name,
        "total_tool_calls": sum(tool_calls_by_name.values()),
        "final_answer_preview": (final_answer or "")[:300],
    }


async def run_variant(label: str, *, with_ptc: bool) -> dict:
    print(f"\n{'='*70}")
    print(f"=== {label}")
    print(f"{'='*70}")
    agent = await build_agent(with_ptc=with_ptc)
    cfg = {"configurable": {"thread_id": f"spike3-{uuid.uuid4().hex[:8]}"}}

    print(f"[run] {VLAN_QUERY!r}")
    t0 = time.time()
    state = await agent.ainvoke(
        {"messages": [{"role": "user", "content": VLAN_QUERY}]},
        config=cfg,
    )
    wall = time.time() - t0
    s = summarise(state)
    s["wall_seconds"] = wall
    s["label"] = label
    print(f"[done] wall={wall:.1f}s  tools={s['total_tool_calls']}  breakdown={s['tool_calls_by_name']}")
    print(f"[answer preview] {s['final_answer_preview']}")
    return s


async def main():
    load_dotenv()
    # Match production: Workaround B's HarnessProfile (BASE_AGENT_PROMPT suppressed,
    # TodoListMiddleware excluded). Required because we build the agent fresh in
    # this script and netbox_agent.py's module-level register_harness_profile
    # hasn't been imported (we don't import NetBoxDeepAgent).
    profile = HarnessProfile(
        base_system_prompt="",
        excluded_middleware=frozenset({"TodoListMiddleware"}),
    )
    for provider in ("ollama", "openai"):
        register_harness_profile(provider, profile)

    a = await run_variant("VARIANT A — production baseline (no PTC)", with_ptc=False)
    b = await run_variant("VARIANT B — production + CodeInterpreterMiddleware", with_ptc=True)

    print(f"\n{'='*70}")
    print("=== COMPARISON")
    print(f"{'='*70}")
    print(f"  No PTC: {a['wall_seconds']:.1f}s, {a['total_tool_calls']} tool calls — {a['tool_calls_by_name']}")
    print(f"  + PTC:  {b['wall_seconds']:.1f}s, {b['total_tool_calls']} tool calls — {b['tool_calls_by_name']}")
    delta_pct = (b['wall_seconds'] - a['wall_seconds']) / a['wall_seconds'] * 100
    sign = '+' if delta_pct >= 0 else ''
    print(f"  Δ wall time: {sign}{delta_pct:.1f}%  ({'REGRESSION' if delta_pct > 0 else 'improvement'})")
    eval_calls = b['tool_calls_by_name'].get('eval', 0)
    direct_calls = sum(v for k, v in b['tool_calls_by_name'].items() if k.startswith('netbox_'))
    print(f"  Variant B mechanism: {eval_calls} eval calls, {direct_calls} direct netbox_* calls")
    if eval_calls > 0 and direct_calls == 0:
        print(f"  → Model committed to PTC. Wall-time delta is the real PTC signal.")
    elif direct_calls > 0 and eval_calls == 0:
        print(f"  → Model ignored PTC entirely. Skill content or instinct steered it to direct calls.")
    else:
        print(f"  → Model mixed both mechanisms. Less clean comparison.")


if __name__ == "__main__":
    asyncio.run(main())
