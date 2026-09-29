"""Probe llama-server's /health and /slots (both live OUTSIDE /v1)."""

from typing import Any

import httpx


async def probe(base_url: str, timeout: float = 2.0) -> dict[str, Any]:
    """Return {"ok": bool, "slot_busy", "n_ctx", "prompt_cache_tokens"}; ok=False on any error."""
    result: dict[str, Any] = {
        "ok": False,
        "slot_busy": None,
        "n_ctx": None,
        "prompt_cache_tokens": None,
    }
    base = base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            health = await client.get(f"{base}/health")
            result["ok"] = health.status_code == 200 and health.json().get("status") == "ok"
            slots = await client.get(f"{base}/slots")
            if slots.status_code == 200:
                data = slots.json()
                if isinstance(data, list) and data:
                    slot = data[0]
                    result["slot_busy"] = bool(slot.get("is_processing"))
                    result["n_ctx"] = slot.get("n_ctx")
                    result["prompt_cache_tokens"] = slot.get("n_prompt_tokens_cache")
    except (httpx.HTTPError, ValueError):
        result["ok"] = False
    return result
