"""Durable LangGraph checkpoints for the web chat.

The web server is the only consumer of a persistent checkpointer: the CLI and the
evaluation harnesses keep NetBoxDeepAgent's default InMemorySaver so every process
starts with fresh memory. The saver's aiosqlite connection lives for the whole FastAPI
lifespan; leaving the context manager closes it, so callers must keep the agent inside.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from ..agents.netbox_agent import PROJECT_ROOT
from ..utils.logging import get_logger

logger = get_logger(__name__)


def resolve_checkpoint_path(path: str) -> Path:
    """Absolute database path; relative values are anchored at PROJECT_ROOT, not the cwd."""
    p = Path(path).expanduser()
    return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()


@asynccontextmanager
async def open_checkpointer(path: str) -> AsyncIterator[AsyncSqliteSaver]:
    """Open (and create) the SQLite checkpoint store for the lifetime of the block.

    Any OSError / sqlite error propagates: a web server that cannot persist memory must
    fail to start rather than silently fall back to RAM.
    """
    db = resolve_checkpoint_path(path)
    db.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Opening checkpoint store", path=str(db))
    async with AsyncSqliteSaver.from_conn_string(str(db)) as saver:
        await saver.setup()
        yield saver
    logger.info("Checkpoint store closed", path=str(db))
