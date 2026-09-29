"""Build LangSmith trace links for web turns.

The web layer mints a run id per turn and passes it as the LangGraph root `run_id`, so the
LangSmith trace of that turn is addressable before it finishes. The organisation and project
ids the URL needs are resolved once at startup (best effort; no link when tracing is off).
"""

import os
from dataclasses import dataclass

from ..utils.logging import get_logger

logger = get_logger(__name__)

LANGSMITH_HOST = "https://smith.langchain.com"


def tracing_enabled() -> bool:
    flag = os.getenv("LANGCHAIN_TRACING_V2", os.getenv("LANGSMITH_TRACING", "false"))
    return flag.strip().lower() in ("1", "true", "yes") and bool(
        os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY")
    )


@dataclass(frozen=True)
class TraceLinker:
    tenant_id: str
    project_id: str
    project_name: str
    host: str = LANGSMITH_HOST

    def url_for(self, run_id: str) -> str:
        return (
            f"{self.host}/o/{self.tenant_id}/projects/p/{self.project_id}"
            f"/r/{run_id}?trace_id={run_id}"
        )


def list_thread_runs(linker: TraceLinker, thread_id: str, limit: int = 100) -> list[dict]:
    """Root runs of a LangGraph thread, oldest first. Sync: call from a thread.

    Used to backfill trace links for turns that ran before the web layer minted run ids
    (or in another client): LangGraph stamps `thread_id` into every run's metadata.
    """
    from langsmith import Client

    flt = f'and(eq(metadata_key, "thread_id"), eq(metadata_value, "{thread_id}"))'
    runs = Client().list_runs(
        project_name=linker.project_name, is_root=True, filter=flt, limit=limit
    )
    out = []
    for r in sorted(runs, key=lambda r: r.start_time):
        rid = str(r.id)
        out.append(
            {
                "run_id": rid,
                "start_time": r.start_time.isoformat(),
                "end_time": r.end_time.isoformat() if r.end_time else None,
                "status": r.status,
                "trace_url": linker.url_for(rid),
            }
        )
    return out


def resolve_trace_linker() -> TraceLinker | None:
    """Look up tenant + project ids via the LangSmith API. Sync: call from a thread."""
    if not tracing_enabled():
        return None
    project_name = os.getenv("LANGCHAIN_PROJECT") or os.getenv("LANGSMITH_PROJECT") or "default"
    try:
        from langsmith import Client

        project = Client().read_project(project_name=project_name)
        tenant_id = getattr(project, "tenant_id", None)
        if not tenant_id:
            logger.warning("LangSmith project has no tenant_id; trace links disabled")
            return None
        linker = TraceLinker(
            tenant_id=str(tenant_id), project_id=str(project.id), project_name=project_name
        )
        logger.info("Trace links enabled", project=project_name)
        return linker
    except Exception as e:  # noqa: BLE001 - links are optional; never block startup
        logger.warning("Could not resolve LangSmith project; trace links disabled", error=str(e))
        return None
