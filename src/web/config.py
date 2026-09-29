"""Configuration for the web chat server.

load_dotenv() runs FIRST, before LLM_BACKEND is read - see src/main.py:229-252 for why the
ordering matters (reading the backend before .env is loaded silently picks Ollama).
"""

import os

from dotenv import load_dotenv

load_dotenv()

from pydantic import BaseModel, Field  # noqa: E402

from ..utils.config import NetBoxConfig, load_config, load_netbox_config  # noqa: E402


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "")


class WebConfig(BaseModel):
    """Non-secret settings for the web layer. Ports live here and nowhere else."""

    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8010)
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3010", "http://127.0.0.1:3010"]
    )
    max_queue: int = Field(default=4, ge=0)
    tool_result_preview_chars: int = Field(default=2000, ge=100)
    heartbeat_s: float = Field(default=15.0, gt=0)
    backend: str = Field(default="ollama")
    model_name: str = Field(default="")
    llama_base_url: str = Field(default="http://localhost:58123")
    n_ctx: int = Field(default=131072, gt=0)
    enable_graphql: bool = Field(default=True)


def load_web_config() -> tuple[WebConfig, NetBoxConfig]:
    """Load web + NetBox config, mirroring the backend-aware branch in src/main.py.

    On the llamacpp backend we must NOT route through load_config(): OllamaConfig validates
    OLLAMA_MODEL against a prefix allow-list that has no GGUF pattern and would raise.
    """
    backend = os.getenv("LLM_BACKEND", "ollama")

    if backend == "llamacpp":
        netbox_config = load_netbox_config()
        model_name = os.getenv("LLAMACPP_MODEL", "Qwen_Qwen3-14B-Q5_K_M.gguf")
    else:
        ollama_config, netbox_config = load_config()
        model_name = ollama_config.model

    llama_v1 = os.getenv("LLAMACPP_BASE_URL", "http://localhost:58123/v1").rstrip("/")
    # /health and /slots are NOT under /v1.
    llama_base = llama_v1[:-3] if llama_v1.endswith("/v1") else llama_v1

    origins = [
        o.strip()
        for o in os.getenv("WEB_CORS_ORIGINS", "http://localhost:3010,http://127.0.0.1:3010").split(
            ","
        )
        if o.strip()
    ]

    web_config = WebConfig(
        host=os.getenv("WEB_HOST", "127.0.0.1"),
        port=int(os.getenv("WEB_PORT", "8010")),
        cors_origins=origins,
        max_queue=int(os.getenv("WEB_MAX_QUEUE", "4")),
        tool_result_preview_chars=int(os.getenv("WEB_TOOL_RESULT_PREVIEW_CHARS", "2000")),
        heartbeat_s=float(os.getenv("WEB_HEARTBEAT_S", "15")),
        backend=backend,
        model_name=model_name,
        llama_base_url=llama_base,
        n_ctx=int(os.getenv("LLAMACPP_N_CTX", "131072")),
        enable_graphql=_env_bool("ENABLE_GRAPHQL", True),
    )
    return web_config, netbox_config
