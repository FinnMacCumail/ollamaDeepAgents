"""LangGraph stream -> wire chunk translation."""

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from src.web.events import TurnStats, finish, translate

N_CTX = 131072


def _usage_chunk(input_tokens, output_tokens, cache_read=0, timings=None):
    return AIMessageChunk(
        content="",
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "input_token_details": {"cache_read": cache_read},
        },
        response_metadata={"timings": timings} if timings else {},
    )


def test_text_delta():
    stats = TurnStats(n_ctx=N_CTX)
    out = translate(
        "messages", (AIMessageChunk(content="Hel"), {"langgraph_node": "model"}), stats, 2000
    )
    assert [c.type for c in out] == ["text"]
    assert out[0].content == "Hel"
    assert stats.text_chars == 3


def test_text_delta_from_blocks():
    stats = TurnStats(n_ctx=N_CTX)
    chunk = AIMessageChunk(content=[{"type": "text", "text": "abc"}])
    out = translate("messages", (chunk, {}), stats, 2000)
    assert out[0].content == "abc"


def test_finish_reason_recorded():
    stats = TurnStats(n_ctx=N_CTX)
    chunk = AIMessageChunk(content="", response_metadata={"finish_reason": "length"})
    translate("messages", (chunk, {}), stats, 2000)
    assert stats.finish_reason == "length"


def test_tool_use_and_result():
    ai = AIMessage(
        content="",
        tool_calls=[
            {"id": "c1", "name": "netbox_get_objects", "args": {"object_type": "dcim.site"}}
        ],
    )
    tm = ToolMessage(
        content="TOOL_VALIDATION_ERROR: multi-hop filter",
        tool_call_id="c1",
        name="netbox_get_objects",
    )
    stats = TurnStats(n_ctx=N_CTX)
    a = translate("updates", {"model": {"messages": [ai]}}, stats, 2000)
    b = translate("updates", {"tools": {"messages": [tm]}}, stats, 2000)
    assert a[0].type == "tool_use"
    assert a[0].metadata["name"] == "netbox_get_objects"
    assert a[0].metadata["args"] == {"object_type": "dcim.site"}
    assert b[0].type == "tool_result"
    assert b[0].metadata["status"] == "validation_error"
    assert b[0].metadata["call_id"] == "c1"
    assert stats.tool_calls == 1


def test_api_error_and_ok_status():
    stats = TurnStats(n_ctx=N_CTX)
    err = ToolMessage(content="TOOL_API_ERROR: 400", tool_call_id="c2", name="t")
    ok = ToolMessage(content='{"count": 1}', tool_call_id="c3", name="t")
    out = translate("updates", {"tools": {"messages": [err, ok]}}, stats, 2000)
    assert [c.metadata["status"] for c in out] == ["api_error", "ok"]


def test_large_tool_result_is_previewed():
    stats = TurnStats(n_ctx=N_CTX)
    tm = ToolMessage(content="x" * 5000, tool_call_id="c1", name="t")
    out = translate("updates", {"tools": {"messages": [tm]}}, stats, 2000)
    assert len(out[0].content) == 2000
    assert out[0].metadata["truncated"] is True


def test_middleware_nodes_ignored():
    stats = TurnStats(n_ctx=N_CTX)
    tm = ToolMessage(content="ignored", tool_call_id="c1", name="t")
    out = translate(
        "updates", {"FilterErrorRecoveryMiddleware.after_model": {"messages": [tm]}}, stats, 2000
    )
    assert out == []


def test_usage_chunk_with_timings():
    stats = TurnStats(n_ctx=N_CTX)
    chunk = _usage_chunk(
        9280,
        412,
        cache_read=7900,
        timings={
            "prompt_per_second": 126.4,
            "predicted_per_second": 10.8,
            "prompt_ms": 875.4,
            "predicted_ms": 38148.0,
        },
    )
    out = translate("messages", (chunk, {}), stats, 2000)
    assert [c.type for c in out] == ["usage"]
    m = out[0].metadata
    assert m["call_index"] == 1
    assert m["input_tokens"] == 9280
    assert m["cache_read"] == 7900
    assert m["decode_tps"] == 10.8
    assert m["n_ctx"] == N_CTX
    assert m["context_pct"] == 7.1
    assert stats.usage.model_calls == 1
    assert stats.usage.context_start == 9280


def test_usage_without_timings_is_none_not_zero():
    stats = TurnStats(n_ctx=N_CTX)
    out = translate("messages", (_usage_chunk(100, 5), {}), stats, 2000)
    assert out[0].metadata["prefill_tps"] is None
    assert out[0].metadata["decode_tps"] is None


def test_compaction_emitted_once():
    stats = TurnStats(n_ctx=N_CTX)
    a = translate("messages", (_usage_chunk(12000, 10), {}), stats, 2000)
    b = translate("messages", (_usage_chunk(4000, 10), {}), stats, 2000)
    c = translate("messages", (_usage_chunk(4500, 10), {}), stats, 2000)
    assert [x.type for x in a] == ["usage"]
    assert [x.type for x in b] == ["context_compacted", "usage"]
    assert b[0].metadata == {"before_tokens": 12000, "after_tokens": 4000}
    assert [x.type for x in c] == ["usage"]
    assert stats.usage.compacted is True


def test_finish_done_totals():
    stats = TurnStats(n_ctx=N_CTX)
    translate("messages", (AIMessageChunk(content="answer"), {}), stats, 2000)
    translate("messages", (_usage_chunk(9000, 100, cache_read=8000), {}), stats, 2000)
    translate("messages", (_usage_chunk(11000, 300, cache_read=9000), {}), stats, 2000)
    done = finish(stats, 12.34, "t1")
    assert done.type == "done" and done.completed is True
    u = done.metadata["usage"]
    assert u["model_calls"] == 2
    assert u["prompt_tokens_total"] == 20000
    assert u["cache_read_total"] == 17000
    assert u["completion_tokens_total"] == 400
    assert u["context_end"] == 11000
    assert u["context_peak"] == 11000
    assert u["elapsed_s"] == 12.34
    assert done.metadata["thread_id"] == "t1"


def test_finish_length_with_no_text_is_error():
    stats = TurnStats(n_ctx=N_CTX, text_chars=0, finish_reason="length")
    out = finish(stats, 1.0, "t1")
    assert out.type == "error"
    assert out.metadata["kind"] == "length"
    assert "usage" in out.metadata


def test_finish_length_with_text_is_done():
    stats = TurnStats(n_ctx=N_CTX, text_chars=10, finish_reason="length")
    assert finish(stats, 1.0, "t1").type == "done"
