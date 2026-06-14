"""Run the NetBox benchmark dataset across a matrix of model variants.

Per the research doc §5.2 option B: single process, one DeepAgent built per
(backend, model_name) tuple, each model's runs grouped under its own
LangSmith experiment_prefix so the comparison view sorts as a leaderboard.

Usage:
    python -m tests.eval.run_matrix                    # default 3-model matrix
    EVAL_MODELS="ollama:deepseek-v4-pro:cloud,ollama:qwen3:14b" \\
        python -m tests.eval.run_matrix                # custom matrix
    EVAL_MAX_CONCURRENCY=1 python -m tests.eval.run_matrix  # serialize examples

The default model set is intentionally small (3 entries) — frontier cloud,
smaller cloud, and a representative local model. Extend it via env once the
first run looks clean. Each per-model run = (4 dataset questions × 3
evaluators) = ~12 trials and takes wall-time roughly proportional to the
slowest question's baseline (the cross-relationship VLAN at ~70s).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Awaitable, Callable

from langsmith import Client, aevaluate

from src.agents.netbox_agent import create_netbox_agent, NetBoxDeepAgent
from tests.eval.dataset import BENCHMARK_EXAMPLES, DATASET_NAME, ensure_dataset
from tests.eval.evaluators import ALL_EVALUATORS

# (backend, model_name) tuples. Backend matches LLM_BACKEND env values
# accepted by NetBoxDeepAgent: "ollama" or "llamacpp".
#
# Full Ollama Cloud frontier sweep (2026-06-07). Ordered for early-result
# visibility: anchor model first, then by family for clean leaderboard
# grouping. The 397b qwen runs last (likely slowest single model).
# Local-model runs use `EVAL_MODELS="ollama:qwen2.5:32b-instruct-q4_K_M,..."`
# to override; they're not in the cloud sweep default since the harness's
# primary axis is now cross-family cloud comparison per the research doc.
DEFAULT_MODELS: list[tuple[str, str]] = [
    ("ollama", "deepseek-v4-pro:cloud"),            # baseline anchor (winner of prior runs)
    ("ollama", "deepseek-v4-flash:cloud"),          # same family, smaller MoE
    ("ollama", "minimax-m3:cloud"),                 # MiniMax (known format-clumsy)
    ("ollama", "nemotron-3-ultra:cloud"),           # NVIDIA Nemotron flagship
    ("ollama", "nemotron-3-super:cloud"),           # NVIDIA Nemotron, smaller MoE
    ("ollama", "gpt-oss:120b-cloud"),               # OpenAI gpt-oss frontier
    ("ollama", "kimi-k2.6:cloud"),                  # Moonshot Kimi (family-coverage)
    ("ollama", "glm-5:cloud"),                      # Z.ai GLM (LangChain reference baseline)
    ("ollama", "gemini-3-flash-preview:cloud"),     # Google Gemini
    ("ollama", "qwen3.5:397b-cloud"),               # Alibaba Qwen frontier
]


def _parse_models_env() -> list[tuple[str, str]] | None:
    """EVAL_MODELS="backend:model_name,backend:model_name" override."""
    raw = os.getenv("EVAL_MODELS")
    if not raw:
        return None
    out: list[tuple[str, str]] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        # Split on FIRST colon only — model names can contain colons (e.g. "qwen3:14b")
        backend, _, model = entry.partition(":")
        if not backend or not model:
            raise ValueError(f"EVAL_MODELS entry malformed: {entry!r} (expected backend:model_name)")
        out.append((backend.strip(), model.strip()))
    return out


def _experiment_prefix(backend: str, model_name: str) -> str:
    """LangSmith-safe experiment prefix that round-trips backend+model identity."""
    safe = model_name.replace(":", "-").replace("/", "-")
    return f"{backend}-{safe}"


async def _run_query_capturing_state(agent: NetBoxDeepAgent, question: str) -> dict:
    """Bypass the streaming filter and call the compiled deep agent directly
    so we can read the full final state — needed for tool_call_count and
    for getting the answer text from the final AI message reliably.

    Each call uses a fresh thread_id so the matrix's per-question runs don't
    accumulate conversation state (matrix runs are stateless by design;
    interactive `main.py` is what the rolling thread_id is for).
    """
    config = {"configurable": {"thread_id": uuid.uuid4().hex}}
    final_state = await agent.agent.ainvoke(
        {"messages": [{"role": "user", "content": question}]},
        config=config,
    )
    messages = final_state.get("messages", [])

    # Tool call count: every AIMessage may carry tool_calls; sum across history.
    tool_call_count = 0
    final_answer = ""
    for msg in messages:
        calls = getattr(msg, "tool_calls", None)
        if calls:
            tool_call_count += len(calls)
        # Last AI message with content (and no tool_calls) is the final answer.
        if (
            getattr(msg, "type", None) == "ai"
            and getattr(msg, "content", None)
            and not calls
        ):
            final_answer = msg.content

    return {"answer": final_answer, "tool_call_count": tool_call_count}


def _build_target(agent: NetBoxDeepAgent) -> Callable[[dict], Awaitable[dict]]:
    """Wrap the agent as an async LangSmith target function."""
    async def target(inputs: dict) -> dict:
        return await _run_query_capturing_state(agent, inputs["question"])
    return target


def _find_completed_experiment(
    client: Client,
    dataset_id: str,
    prefix: str,
    expected_examples: int,
) -> str | None:
    """Return the name of a fully-scored existing experiment matching `prefix`
    on this dataset, or None.

    "Fully scored" means: >= expected_examples root runs, AND every root run
    has a non-None `tool_calls` score. The tool_calls evaluator is the
    discriminator because it returns None when `outputs["tool_call_count"]`
    is missing — which only happens if the target function failed before
    capturing state (e.g. an Ollama 429 raised inside `_run_query_capturing_state`
    before it could compute and return the count). Successful runs always
    have an integer tool_call_count, even zero — so a non-None score proves
    the target executed cleanly.

    Why not entity_coverage: it returns 0.0 (not None) for empty answers,
    so a 429-killed run with answer="" gets score=0.0 and would falsely
    pass an "all non-None" check. tool_calls correctly differentiates.

    Used to make the matrix runner re-entrant after rate-limit failures —
    re-running picks up only what's missing instead of re-spending on what's
    already on LangSmith.
    """
    candidates = client.list_projects(reference_dataset_id=dataset_id)
    for proj in candidates:
        if not proj.name.startswith(prefix + "-"):
            continue
        runs = list(client.list_runs(project_name=proj.name, is_root=True))
        if len(runs) < expected_examples:
            continue
        all_scored = True
        for r in runs:
            fb = {f.key: f.score for f in client.list_feedback(run_ids=[r.id])}
            if fb.get("tool_calls") is None:
                all_scored = False
                break
        if all_scored:
            return proj.name
    return None


def _experiment_was_quota_throttled(
    client: Client, experiment_name: str, n_examples: int
) -> bool:
    """Detect post-hoc whether the experiment we just ran was 429-throttled.

    We scan the root runs' error fields for Ollama's quota error signature.
    If at least half the runs failed with that signature, we treat the matrix
    as quota-exhausted and abort the outer loop — every subsequent model
    would also instantly 429, polluting LangSmith with junk experiments AND
    pushing the rolling-window reset timer further out.
    """
    runs = list(client.list_runs(project_name=experiment_name, is_root=True))
    if not runs:
        return False
    quota_hits = 0
    for r in runs:
        err = getattr(r, "error", None) or ""
        if "session usage limit" in err.lower() or "status code: 429" in err:
            quota_hits += 1
    return quota_hits >= max(2, n_examples // 2 + 1)


async def _evaluate_one(
    backend: str,
    model_name: str,
    max_concurrency: int,
    client: Client,
    dataset_id: str,
) -> dict:
    """Run one model's evaluation; return {'skipped': bool, 'quota_exhausted': bool}."""
    print(f"\n=== {backend}:{model_name} ===", flush=True)
    prefix = _experiment_prefix(backend, model_name)
    # Skip the lookup when EVAL_FORCE_RERUN=1 — used for regression tests
    # (e.g. validating a framework upgrade) where we want fresh experiments
    # alongside historical ones for comparison, not a SKIP that bypasses
    # actual scoring.
    if os.getenv("EVAL_FORCE_RERUN", "").strip() not in ("", "0", "false", "False"):
        existing = None
    else:
        existing = _find_completed_experiment(
            client, dataset_id, prefix, expected_examples=len(BENCHMARK_EXAMPLES)
        )
    if existing:
        print(f"  SKIP — already completed: {existing}", flush=True)
        return {"skipped": True, "quota_exhausted": False}

    agent = await create_netbox_agent(backend=backend, model_name=model_name)
    try:
        target = _build_target(agent)
        results = await aevaluate(
            target,
            data=DATASET_NAME,
            evaluators=ALL_EVALUATORS,
            experiment_prefix=prefix,
            max_concurrency=max_concurrency,
            metadata={"backend": backend, "model": model_name},
        )
        print(f"  experiment: {results.experiment_name}", flush=True)
        quota_dead = _experiment_was_quota_throttled(
            client, results.experiment_name, len(BENCHMARK_EXAMPLES)
        )
        if quota_dead:
            print(
                f"  QUOTA EXHAUSTED — most runs 429'd. Aborting matrix to "
                f"avoid pushing the rolling-window reset further out.",
                flush=True,
            )
        return {"skipped": False, "quota_exhausted": quota_dead}
    finally:
        await agent.cleanup()


async def main() -> None:
    dataset = ensure_dataset()  # idempotent
    client = Client()

    models = _parse_models_env() or DEFAULT_MODELS
    # Serialize per-example calls by default — NetBox MCP server is stdio and
    # the agent's conversation state is per-thread; parallel calls on one
    # process would interleave MCP requests. Override via env if needed.
    max_concurrency = int(os.getenv("EVAL_MAX_CONCURRENCY", "1"))

    print(f"Matrix: {len(models)} model(s) × {DATASET_NAME}", flush=True)
    for backend, model in models:
        print(f"  - {backend}:{model}", flush=True)

    aborted = False
    for backend, model in models:
        try:
            result = await _evaluate_one(
                backend, model, max_concurrency, client, str(dataset.id)
            )
            if result.get("quota_exhausted"):
                aborted = True
                remaining = [
                    f"{b}:{m}" for b, m in models[models.index((backend, model)) + 1:]
                ]
                if remaining:
                    print(
                        f"\nSkipping {len(remaining)} remaining model(s) due to quota: "
                        f"{', '.join(remaining)}",
                        flush=True,
                    )
                break
        except Exception as e:
            # One model failing shouldn't abort the matrix — log and continue.
            print(f"  FAILED {backend}:{model}: {type(e).__name__}: {e}", flush=True)
    if aborted:
        print(
            "\nMatrix aborted on quota. Re-run after Ollama Cloud session "
            "limit resets (see https://ollama.com/settings) — the skip-completed "
            "logic will pick up only the un-run models.",
            flush=True,
        )


if __name__ == "__main__":
    asyncio.run(main())
