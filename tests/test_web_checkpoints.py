"""Durable checkpoint store: SQLite round-trip, reload across instances, rollback recipe."""

import asyncio
import sqlite3
from typing import Annotated, NotRequired, TypedDict

import pytest
from langchain.agents.middleware.types import PrivateStateAttr
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Send

from src.agents.netbox_agent import NetBoxDeepAgent
from src.web.checkpoints import open_checkpointer, resolve_checkpoint_path


class State(TypedDict):
    messages: Annotated[list, add_messages]
    _priv: Annotated[NotRequired[dict | None], PrivateStateAttr]


def _graph():
    """model -> tools -> slow, like the agent loop; `slow` is where cancels land."""

    def model(s):
        n = len(s["messages"])
        return {
            "messages": [
                AIMessage(content="", tool_calls=[{"id": f"c{n}", "name": "t", "args": {}}])
            ],
            "_priv": {"cutoff_index": 3, "summary": "x"},
        }

    def tools(s):
        return {
            "messages": [
                ToolMessage(content="result", tool_call_id=s["messages"][-1].tool_calls[0]["id"])
            ]
        }

    async def slow(s):
        await asyncio.sleep(0.3)
        return {"messages": [AIMessage(content="final answer")]}

    g = StateGraph(State)
    g.add_node("model", model)
    g.add_node("tools", tools)
    g.add_node("slow", slow)
    g.add_edge(START, "model")
    g.add_edge("model", "tools")
    g.add_edge("tools", "slow")
    g.add_edge("slow", END)
    return g


def test_resolve_relative_to_project_root(tmp_path):
    from src.agents.netbox_agent import PROJECT_ROOT

    assert resolve_checkpoint_path("data/x.sqlite") == (PROJECT_ROOT / "data/x.sqlite").resolve()
    assert resolve_checkpoint_path(str(tmp_path / "y.sqlite")) == tmp_path / "y.sqlite"


async def test_state_survives_a_new_saver_instance(tmp_path):
    db = str(tmp_path / "ck.sqlite")
    cfg = {"configurable": {"thread_id": "abc"}}

    async with open_checkpointer(db) as saver:
        app = _graph().compile(checkpointer=saver)
        await app.ainvoke({"messages": [HumanMessage(content="q1")]}, cfg)
        first = await app.aget_state(cfg)
    assert first.values["_priv"] == {"cutoff_index": 3, "summary": "x"}

    # "process restart": a brand-new saver over the same file
    async with open_checkpointer(db) as saver2:
        app2 = _graph().compile(checkpointer=saver2)
        st = await app2.aget_state(cfg)
        assert [m.content for m in st.values["messages"]] == [
            m.content for m in first.values["messages"]
        ]
        assert st.values["_priv"] == first.values["_priv"]
        assert st.next == ()
        await app2.ainvoke({"messages": [HumanMessage(content="q2")]}, cfg)
        assert len((await app2.aget_state(cfg)).values["messages"]) == 8

        unknown = await app2.aget_state({"configurable": {"thread_id": "nope"}})
        assert unknown.values == {}
        await saver2.adelete_thread("abc")
        assert (await app2.aget_state(cfg)).values == {}


async def test_unwritable_path_raises(tmp_path):
    bad = tmp_path / "ro"
    bad.mkdir()
    bad.chmod(0o500)
    try:
        with pytest.raises((OSError, sqlite3.OperationalError)):
            async with open_checkpointer(str(bad / "sub" / "ck.sqlite")):
                pass
    finally:
        bad.chmod(0o700)


async def test_rollback_recipe_clears_orphans_and_pending_task():
    """What NetBoxDeepAgent.rollback_turn does, shown on the bare graph."""
    saver = InMemorySaver()
    app = _graph().compile(checkpointer=saver)
    cfg = {"configurable": {"thread_id": "t"}}
    await app.ainvoke({"messages": [HumanMessage(content="q1")]}, cfg)
    keep = {m.id for m in (await app.aget_state(cfg)).values["messages"]}

    task = asyncio.create_task(app.ainvoke({"messages": [HumanMessage(content="q2")]}, cfg))
    await asyncio.sleep(0.1)  # cancel inside `slow`
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    st = await app.aget_state(cfg)
    assert st.next == ("slow",)
    assert len(st.values["messages"]) == 7  # 4 kept + user + ai(tool_call) + tool

    orphans = [m.id for m in st.values["messages"] if m.id not in keep]
    # Attribute the write to the node that routes to END ("slow" here), otherwise
    # aupdate_state schedules that node's successor and `next` stays non-empty.
    await app.aupdate_state(
        cfg, {"messages": [RemoveMessage(id=i) for i in orphans]}, as_node="slow"
    )
    st2 = await app.aget_state(cfg)
    assert st2.next == ()
    assert {m.id for m in st2.values["messages"]} == keep

    await app.ainvoke({"messages": [HumanMessage(content="q3")]}, cfg)
    assert len((await app.aget_state(cfg)).values["messages"]) == 8


async def test_agent_rollback_turn_uses_graph(monkeypatch):
    """NetBoxDeepAgent.rollback_turn / message_ids / thread_exists on a bare graph."""
    agent = NetBoxDeepAgent(netbox_config=None, checkpointer=InMemorySaver())
    agent.agent = _graph().compile(checkpointer=agent.checkpointer)
    cfg = {"configurable": {"thread_id": "t"}}
    assert await agent.thread_exists("t") is False
    assert await agent.message_ids("t") == set()

    await agent.agent.ainvoke({"messages": [HumanMessage(content="q1")]}, cfg)
    keep = await agent.message_ids("t")
    assert await agent.thread_exists("t") is True and len(keep) == 4

    task = asyncio.create_task(agent.agent.ainvoke({"messages": [HumanMessage(content="q2")]}, cfg))
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert agent._rollback_node() == "slow"  # discovered from the graph, not hardcoded
    removed = await agent.rollback_turn("t", keep)
    assert removed == 3
    assert await agent.message_ids("t") == keep
    assert (await agent.agent.aget_state(cfg)).next == ()
    assert await agent.rollback_turn("t", keep) == 0  # idempotent

    await agent.delete_thread("t")
    assert await agent.thread_exists("t") is False


def test_default_checkpointer_is_in_memory_and_injection_wins():
    sentinel = InMemorySaver()
    assert isinstance(NetBoxDeepAgent().checkpointer, InMemorySaver)
    assert NetBoxDeepAgent(checkpointer=sentinel).checkpointer is sentinel


def _send_graph():
    """Agent-shaped graph: model emits two tool calls, each runs as its own Send task
    (how langchain's ToolNode dispatches); `slow` is where a cancel lands while `fast`
    has already produced a PENDING write."""
    import itertools

    counter = itertools.count()

    def model(s):
        last = s["messages"][-1] if s["messages"] else None
        if isinstance(last, HumanMessage):
            n = next(counter)
            return {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {"id": f"fast{n}", "name": "fast", "args": {}},
                            {"id": f"slow{n}", "name": "slow", "args": {}},
                        ],
                    )
                ]
            }
        return {"messages": [AIMessage(content="final")]}

    async def tool_task(call):
        if call["name"] == "slow":
            await asyncio.sleep(0.5)
        return {
            "messages": [ToolMessage(content=f"{call['name']} result", tool_call_id=call["id"])]
        }

    def route(s):
        if not s["messages"]:
            return END
        last = s["messages"][-1]
        if getattr(last, "tool_calls", None):
            return [Send("tools", c) for c in last.tool_calls]
        return END

    g = StateGraph(State)
    g.add_node("model", model)
    g.add_node("tools", tool_task)
    g.add_edge(START, "model")
    g.add_conditional_edges("model", route, ["tools", END])
    g.add_edge("tools", "model")
    return g


async def test_rollback_drops_pending_parallel_tool_result(tmp_path):
    """The real-agent leak: a tool that finished before the cancel lives only as a pending
    write; naive RemoveMessage misses it and the next turn inherits it."""
    async with open_checkpointer(str(tmp_path / "ck.sqlite")) as saver:
        agent = NetBoxDeepAgent(netbox_config=None, checkpointer=saver)
        agent.agent = _send_graph().compile(checkpointer=saver)
        cfg = {"configurable": {"thread_id": "t"}}
        await agent.agent.ainvoke({"messages": [HumanMessage(content="q0")]}, cfg)
        keep = await agent.message_ids("t")
        assert len(keep) == 5

        task = asyncio.create_task(
            agent.agent.ainvoke({"messages": [HumanMessage(content="q1")]}, cfg)
        )
        await asyncio.sleep(0.15)  # fast done (pending write), slow running
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        merged = await agent.agent.aget_state(cfg)
        assert merged.next == ("tools",)
        assert any(t.result for t in merged.tasks)  # the finished tool's pending write

        removed = await agent.rollback_turn("t", keep)
        assert removed >= 2  # user + ai(tool_calls) committed; the pending fast result is dropped or removed in pass 2
        after = await agent.agent.aget_state(cfg)
        assert after.next == ()
        assert {m.id for m in after.values["messages"]} == keep

        await agent.agent.ainvoke({"messages": [HumanMessage(content="q2")]}, cfg)
        msgs = (await agent.agent.aget_state(cfg)).values["messages"]
        assert not [
            m for m in msgs if isinstance(m, ToolMessage) and m.tool_call_id in ("fast1", "slow1")
        ]
        assert len(msgs) == 10  # q0 turn (5) + q2 turn (5), nothing from q1
