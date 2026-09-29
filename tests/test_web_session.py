"""TurnRunner: serialisation, queue position, cancellation, ledger."""

import asyncio

import pytest
from langchain_core.messages import AIMessageChunk

from src.web.config import WebConfig
from src.web.session import TurnRunner, sanitise_error


class FakeAgent:
    """Yields a few text deltas and one usage chunk, with awaits so tasks interleave."""

    def __init__(self, deltas=("a", "b"), delay=0.01, fail=False):
        self.deltas = deltas
        self.delay = delay
        self.fail = fail
        self.calls = []

    async def stream_events(self, text, thread_id, run_id=None):
        self.calls.append((text, thread_id))
        self.run_ids = getattr(self, "run_ids", []) + [run_id]
        for d in self.deltas:
            await asyncio.sleep(self.delay)
            yield "messages", (AIMessageChunk(content=d), {})
        if self.fail:
            raise RuntimeError("boom /secret/path")
        yield (
            "messages",
            (
                AIMessageChunk(
                    content="",
                    usage_metadata={"input_tokens": 100, "output_tokens": 10, "total_tokens": 110},
                ),
                {},
            ),
        )


def _cfg(**kw):
    return WebConfig(heartbeat_s=1000, **kw)


async def test_second_turn_queues_and_runs_after_first():
    agent = FakeAgent()
    runner = TurnRunner(agent, _cfg())
    sent_a, sent_b = [], []

    async def send_a(c):
        sent_a.append(c)

    async def send_b(c):
        sent_b.append(c)

    t1 = asyncio.create_task(runner.run(send_a, "ws1", "conv1", "q1"))
    await asyncio.sleep(0.005)  # t1 holds the lock
    t2 = asyncio.create_task(runner.run(send_b, "ws2", "conv2", "q2"))
    await asyncio.sleep(0.005)
    assert runner.running is True
    assert runner.queue_depth == 1
    await asyncio.gather(t1, t2)

    # position = turns ahead: the first starts at once (0), the second waits behind it (1)
    assert sent_a[0].type == "queued" and sent_a[0].metadata["position"] == 0
    assert sent_b[0].type == "queued" and sent_b[0].metadata["position"] == 1
    assert sent_a[-1].type == "done"
    assert sent_b[-1].type == "done"
    # strictly serialised: agent saw q1 fully before q2 started
    assert agent.calls == [("q1", "conv1"), ("q2", "conv2")]
    assert runner.running is False and runner.queue_depth == 0


async def test_cancel_by_owner_frees_lock():
    agent = FakeAgent(deltas=tuple("x" * 50), delay=0.01)
    runner = TurnRunner(agent, _cfg())
    sent = []

    async def send(c):
        sent.append(c)

    t = asyncio.create_task(runner.run(send, "ws1", "conv1", "q"))
    await asyncio.sleep(0.05)
    assert runner.cancel("ws-other") is False  # not the owner
    assert runner.cancel("ws1") is True
    await t
    assert sent[-1].type == "cancelled" and sent[-1].completed is True
    assert runner.running is False
    # lock released: a new turn proceeds
    sent2 = []

    async def send2(c):
        sent2.append(c)

    await runner.run(send2, "ws2", "conv2", "q2")
    assert sent2[-1].type == "done"


async def test_cancel_while_queued_leaves_counter_consistent():
    agent = FakeAgent(deltas=tuple("x" * 20), delay=0.01)
    runner = TurnRunner(agent, _cfg())

    async def sink(c):
        pass

    t1 = asyncio.create_task(runner.run(sink, "ws1", "c1", "q1"))
    await asyncio.sleep(0.005)
    t2 = asyncio.create_task(runner.run(sink, "ws2", "c2", "q2"))
    await asyncio.sleep(0.005)
    assert runner.queue_depth == 1
    t2.cancel()
    with pytest.raises(asyncio.CancelledError):
        await t2
    assert runner.queue_depth == 0
    await t1
    assert agent.calls == [("q1", "c1")]


async def test_queue_full_rejected():
    agent = FakeAgent(deltas=tuple("x" * 20), delay=0.01)
    runner = TurnRunner(agent, _cfg(max_queue=1))
    sent = []

    async def send(c):
        sent.append(c)

    async def sink(c):
        pass

    t1 = asyncio.create_task(runner.run(sink, "ws1", "c1", "q1"))
    await asyncio.sleep(0.005)
    t2 = asyncio.create_task(runner.run(sink, "ws2", "c2", "q2"))
    await asyncio.sleep(0.005)
    await runner.run(send, "ws3", "c3", "q3")
    assert sent[0].type == "error" and sent[0].metadata["kind"] == "queue"
    await asyncio.gather(t1, t2)


async def test_agent_error_becomes_error_chunk_and_is_recorded():
    runner = TurnRunner(FakeAgent(fail=True), _cfg())
    sent = []

    async def send(c):
        sent.append(c)

    await runner.run(send, "ws1", "c1", "q1")
    assert sent[-1].type == "error" and sent[-1].metadata["kind"] == "agent"
    assert "/secret/path" not in sent[-1].content
    assert len(runner.conversation_usage("c1").turns) == 1


async def test_ledger_sums():
    runner = TurnRunner(FakeAgent(), _cfg())

    async def sink(c):
        pass

    await runner.run(sink, "ws1", "c1", "q1")
    await runner.run(sink, "ws1", "c1", "q2")
    u = runner.conversation_usage("c1")
    assert len(u.turns) == 2
    assert u.prompt_tokens_total == 200
    assert u.completion_tokens_total == 20
    assert u.model_calls_total == 2
    assert u.context_end == 100
    assert u.n_ctx == 131072
    assert runner.conversation_usage("unknown").turns == []


def test_sanitise_error():
    assert "[redacted]" in sanitise_error("failed at /home/x/y.py")
    assert sanitise_error("plain text") == "plain text"


async def test_run_id_minted_and_linked():
    from src.web.tracing import TraceLinker

    agent = FakeAgent()
    runner = TurnRunner(agent, _cfg(), trace_linker=TraceLinker("t", "p", "name"))
    sent = []

    async def send(c):
        sent.append(c)

    await runner.run(send, "ws1", "c1", "q1")
    done = sent[-1]
    rid = done.metadata["run_id"]
    assert agent.run_ids == [rid] and len(rid) == 36
    assert (
        done.metadata["trace_url"]
        == f"https://smith.langchain.com/o/t/projects/p/p/r/{rid}?trace_id={rid}"
    )
    assert runner.conversation_usage("c1").turns[0].trace_url == done.metadata["trace_url"]


async def test_no_linker_means_no_url():
    runner = TurnRunner(FakeAgent(), _cfg())
    sent = []

    async def send(c):
        sent.append(c)

    await runner.run(send, "ws1", "c1", "q1")
    assert sent[-1].metadata["run_id"] and sent[-1].metadata["trace_url"] is None
