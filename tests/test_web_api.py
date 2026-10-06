"""FastAPI routes and WebSocket protocol with a fake agent (no llama-server, no NetBox)."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk

from src.web import api as api_module
from src.web.config import WebConfig
from src.web.models import HealthResponse
from src.web.session import TurnRunner
from src.web.tracing import TraceLinker


class FakeAgent:
    def __init__(self):
        self.agent = object()  # "initialised"
        self.histories = {}
        self.cleaned = False

    async def stream_events(self, text, thread_id, run_id=None):
        self.histories.setdefault(thread_id, []).append({"role": "user", "content": text})
        for d in ("Hel", "lo"):
            await asyncio.sleep(0)
            yield "messages", (AIMessageChunk(content=d), {})
        yield (
            "messages",
            (
                AIMessageChunk(
                    content="",
                    usage_metadata={"input_tokens": 50, "output_tokens": 5, "total_tokens": 55},
                ),
                {},
            ),
        )
        self.histories[thread_id].append({"role": "assistant", "content": "Hello"})

    async def get_history(self, thread_id):
        return list(self.histories.get(thread_id, []))

    async def thread_exists(self, thread_id):
        return thread_id in self.histories

    async def message_ids(self, thread_id):
        return set()

    async def rollback_turn(self, thread_id, keep_ids):
        return 0

    async def delete_thread(self, thread_id):
        self.deleted = getattr(self, "deleted", []) + [thread_id]
        self.histories.pop(thread_id, None)

    async def cleanup(self):
        self.cleaned = True


@pytest.fixture
def client(monkeypatch, tmp_path):
    # The lifespan opens a real SQLite checkpoint store; keep it out of the project tree.
    monkeypatch.setenv("WEB_CHECKPOINT_DB", str(tmp_path / "ck.sqlite"))
    monkeypatch.setenv("LLM_BACKEND", "llamacpp")
    monkeypatch.setenv("NETBOX_URL", "http://localhost:8000")
    monkeypatch.setenv("NETBOX_TOKEN", "t")
    fake = FakeAgent()
    probe_result = {"ok": True, "slot_busy": False, "n_ctx": 131072, "prompt_cache_tokens": 0}
    with (
        patch.object(api_module, "_build_agent", AsyncMock(return_value=fake)),
        patch.object(api_module, "probe", AsyncMock(return_value=probe_result)),
        patch.object(
            api_module, "resolve_trace_linker", lambda: TraceLinker("tenant-1", "proj-1", "p")
        ),
        patch.object(
            api_module,
            "list_thread_runs",
            lambda linker, tid, limit=200: (
                [
                    {
                        "run_id": "r1",
                        "start_time": "2026-09-28T18:17:58+00:00",
                        "end_time": "2026-09-28T18:21:40+00:00",
                        "status": "success",
                        "trace_url": linker.url_for("r1"),
                    }
                ]
                if tid == "known"
                else []
            ),
        ),
    ):
        app = api_module.create_app()
        with TestClient(app) as c:
            c.fake = fake
            yield c
    assert fake.cleaned is True


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = HealthResponse(**r.json())
    assert body.status == "healthy" and body.agent_ready is True and body.llama_ok is True


def test_status_has_compaction_trigger(client):
    r = client.get("/status")
    assert r.status_code == 200
    b = r.json()
    assert b["n_ctx"] == 131072
    assert b["compaction_trigger_tokens"] == int(0.85 * 131072)
    assert b["turn_running"] is False and b["queue_depth"] == 0
    assert b["backend"] == "llamacpp"


def test_models_informational(client):
    r = client.get("/models")
    assert r.status_code == 200
    assert r.json()[0]["provider"] == "llamacpp"


def test_ws_full_turn_and_history(client):
    with client.websocket_connect("/ws/chat") as ws:
        first = ws.receive_json()
        assert first["type"] == "connected"
        ws.send_json({"type": "message", "conversation_id": "conv1", "message": "hi"})
        types = []
        text = ""
        while True:
            chunk = ws.receive_json()
            types.append(chunk["type"])
            if chunk["type"] == "text":
                text += chunk["content"]
            if chunk.get("completed"):
                break
        assert types[0] == "queued" and chunk is not None
        assert "usage" in types
        assert types[-1] == "done"
        assert text == "Hello"
        done = chunk
        assert done["metadata"]["usage"]["model_calls"] == 1
        assert done["metadata"]["thread_id"] == "conv1"
        rid = done["metadata"]["run_id"]
        assert len(rid) == 36
        assert (
            done["metadata"]["trace_url"]
            == f"https://smith.langchain.com/o/tenant-1/projects/p/proj-1/r/{rid}?trace_id={rid}"
        )
        assert done["metadata"]["usage"]["trace_url"] == done["metadata"]["trace_url"]

        ws.send_json({"type": "resume", "conversation_id": "conv1"})
        resumed = ws.receive_json()
        assert resumed["type"] == "resumed" and resumed["metadata"]["known"] is True
        assert resumed["metadata"]["turns"] == 1
        assert resumed["metadata"]["conversation_id"] == "conv1"

    r = client.get("/conversations/conv1/messages")
    assert r.status_code == 200
    assert [m["role"] for m in r.json()] == ["user", "assistant"]

    u = client.get("/conversations/conv1/usage").json()
    assert u["prompt_tokens_total"] == 50 and u["model_calls_total"] == 1


def test_ws_protocol_errors_keep_socket_open(client):
    with client.websocket_connect("/ws/chat") as ws:
        ws.receive_json()
        ws.send_text("not json")
        err = ws.receive_json()
        assert err["type"] == "error" and err["metadata"]["kind"] == "protocol"
        ws.send_json({"type": "message", "message": "no conversation id"})
        err = ws.receive_json()
        assert err["type"] == "error"
        ws.send_json({"type": "cancel"})
        err = ws.receive_json()
        assert err["content"] == "Nothing to cancel"
        ws.send_json({"type": "resume", "conversation_id": "nope"})
        resumed = ws.receive_json()
        assert resumed["metadata"] == {"known": False, "turns": 0, "conversation_id": "nope"}
        ws.send_json({"type": "new_conversation"})
        reset = ws.receive_json()
        assert reset["type"] == "reset_complete" and len(reset["metadata"]["thread_id"]) == 32


def test_unknown_conversation_endpoints(client):
    assert client.get("/conversations/nope/messages").status_code == 404
    r = client.get("/conversations/nope/usage")
    assert r.status_code == 200 and r.json()["turns"] == []


def test_web_config_llamacpp_branch(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "llamacpp")
    monkeypatch.setenv("LLAMACPP_MODEL", "qwen3.8-flash-next-UD-Q4_K_XL")
    monkeypatch.setenv("LLAMACPP_BASE_URL", "http://localhost:58123/v1")
    monkeypatch.setenv("NETBOX_URL", "http://localhost:8000")
    monkeypatch.setenv("NETBOX_TOKEN", "t")
    monkeypatch.setenv("WEB_CORS_ORIGINS", "http://a:1, http://b:2")
    from src.web.config import load_web_config

    cfg, nb = load_web_config()
    assert isinstance(cfg, WebConfig)
    assert cfg.model_name == "qwen3.8-flash-next-UD-Q4_K_XL"
    assert cfg.llama_base_url == "http://localhost:58123"
    assert cfg.cors_origins == ["http://a:1", "http://b:2"]
    assert cfg.port == 8010
    assert nb.url == "http://localhost:8000"


def test_runner_is_attached(client):
    assert isinstance(client.app.state.runner, TurnRunner)


def test_conversation_traces_backfill(client):
    r = client.get("/conversations/known/traces")
    assert r.status_code == 200
    rows = r.json()
    assert rows[0]["run_id"] == "r1"
    assert (
        rows[0]["trace_url"]
        == "https://smith.langchain.com/o/tenant-1/projects/p/proj-1/r/r1?trace_id=r1"
    )
    assert client.get("/conversations/unknown/traces").json() == []
    assert client.get("/conversations/bad%20id!/traces").status_code == 422


def test_delete_conversation(client):
    with client.websocket_connect("/ws/chat") as ws:
        ws.receive_json()
        ws.send_json({"type": "message", "conversation_id": "todel", "message": "hi"})
        while not ws.receive_json().get("completed"):
            pass
    assert client.get("/conversations/todel/messages").status_code == 200
    assert client.get("/conversations/todel/usage").json()["turns"]
    r = client.delete("/conversations/todel")
    assert r.status_code == 204
    assert client.fake.deleted == ["todel"]
    assert client.get("/conversations/todel/messages").status_code == 404
    assert client.get("/conversations/todel/usage").json()["turns"] == []
    assert client.delete("/conversations/bad%20id!").status_code == 422
