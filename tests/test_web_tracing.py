"""Trace-link helper."""

from src.web.tracing import TraceLinker, resolve_trace_linker, tracing_enabled


def test_url_shape():
    url = TraceLinker("org", "proj", "name").url_for("abc")
    assert url == "https://smith.langchain.com/o/org/projects/p/proj/r/abc?trace_id=abc"


def test_tracing_disabled_without_flag(monkeypatch):
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    assert tracing_enabled() is False
    assert resolve_trace_linker() is None


def test_tracing_disabled_without_key(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    assert tracing_enabled() is False
