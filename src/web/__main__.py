"""Run the web chat server: ./venv/bin/python -m src.web"""

import os

# The blocking llm.invoke("test") at agent init would stall the event loop; skip it here.
os.environ.setdefault("LLAMACPP_VALIDATE_ON_INIT", "false")

import uvicorn  # noqa: E402

from .config import load_web_config  # noqa: E402


def run() -> None:
    web_config, _ = load_web_config()
    uvicorn.run(
        "src.web.api:app",
        host=web_config.host,
        port=web_config.port,
        ws_ping_interval=20,
        ws_ping_timeout=60,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    run()
