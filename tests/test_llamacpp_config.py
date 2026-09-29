"""Tests for the llama.cpp model factory additions (stream_usage, timings, validate gate)."""

from unittest.mock import patch

from langchain_core.messages import AIMessageChunk

from src.agents.llamacpp_config import LlamaCppChatOpenAI, create_llamacpp_model


def test_create_model_enables_stream_usage(monkeypatch):
    monkeypatch.delenv("LLAMACPP_STREAM_CHUNK_TIMEOUT_S", raising=False)
    llm = create_llamacpp_model("some-alias", validate=False)
    assert isinstance(llm, LlamaCppChatOpenAI)
    assert llm.stream_usage is True
    # default: no silence watchdog (prefill after a big tool result can exceed 120 s)
    assert llm.stream_chunk_timeout is None


def test_stream_chunk_timeout_env_override(monkeypatch):
    monkeypatch.setenv("LLAMACPP_STREAM_CHUNK_TIMEOUT_S", "600")
    llm = create_llamacpp_model("some-alias", validate=False)
    assert llm.stream_chunk_timeout == 600.0


def test_timings_preserved_on_usage_chunk():
    llm = create_llamacpp_model("some-alias", validate=False)
    chunk = {
        "id": "x",
        "object": "chat.completion.chunk",
        "choices": [],
        "usage": {
            "prompt_tokens": 42,
            "completion_tokens": 16,
            "total_tokens": 58,
            "prompt_tokens_details": {"cached_tokens": 30},
        },
        "timings": {"prompt_per_second": 13.7, "predicted_per_second": 13.9, "prompt_ms": 875.4},
    }
    gen = llm._convert_chunk_to_generation_chunk(chunk, AIMessageChunk, None)
    assert gen is not None
    assert gen.message.usage_metadata["input_tokens"] == 42
    assert gen.message.usage_metadata["input_token_details"]["cache_read"] == 30
    assert gen.message.response_metadata["timings"]["predicted_per_second"] == 13.9


def test_validate_gate_env_skips_invoke(monkeypatch):
    monkeypatch.setenv("LLAMACPP_VALIDATE_ON_INIT", "false")
    with patch.object(LlamaCppChatOpenAI, "invoke") as mock_invoke:
        create_llamacpp_model("some-alias", validate=True)
        mock_invoke.assert_not_called()
