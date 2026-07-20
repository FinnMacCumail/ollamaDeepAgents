"""Run the netbox-benchmark-v4 dataset — the Step-4 baseline-vs-GraphQL A/B.

Same machinery as run_matrix_v3, but:
  - Dataset: netbox-benchmark-v4 (corrected-scoring namespace).
  - Evaluators: evaluators.ALL_EVALUATORS — now includes the reference-grounded
    `correctness_judge`, which is surfaced in the leaderboard.
  - EVAL_VARIANT: labels the run "baseline" (default) or "graphql" and appends it
    to each experiment prefix, so the two arms of the A/B are distinct, comparable
    experiments under the same v4 dataset. The A/B is driven by which git branch
    you run from: `master` (no GraphQL tool) => baseline; `feat/graphql-read-tool`
    (GraphQL tool wired in) => graphql. The tool set differs by branch; this
    runner is identical on both.
  - Default model set is the production pair (deepseek-v4-flash + pro); override
    with EVAL_MODELS for a wider sweep.

Usage:
    # on master (no GraphQL):
    EVAL_VARIANT=baseline ./venv/bin/python -m tests.eval.run_matrix_v4
    # on feat/graphql-read-tool (GraphQL wired in):
    EVAL_VARIANT=graphql  ./venv/bin/python -m tests.eval.run_matrix_v4
    # wider sweep:
    EVAL_MODELS="ollama:glm-5:cloud,ollama:kimi-k2.6:cloud" ./venv/bin/python -m tests.eval.run_matrix_v4
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

from langsmith import Client, aevaluate

from src.agents.netbox_agent import create_netbox_agent
from tests.eval.dataset_v4 import (
    BENCHMARK_EXAMPLES_V4,
    DATASET_NAME_V4,
    ensure_dataset_v4,
)
from tests.eval.evaluators import ALL_EVALUATORS
from tests.eval.run_matrix import (
    _build_target,
    _experiment_prefix,
    _experiment_was_quota_throttled,
    _find_completed_experiment,
    _parse_models_env,
)
from tests.eval.run_matrix_v3 import _fetch_feedback

# Default A/B scope: the production pair. Override with EVAL_MODELS.
_DEFAULT_V4_MODELS: list[tuple[str, str]] = [
    ("ollama", "deepseek-v4-flash:cloud"),
    ("ollama", "deepseek-v4-pro:cloud"),
]

_TRACES_DIR = Path(__file__).resolve().parents[2] / "docs" / "traces"
_SCORE_KEYS = ("entity_coverage", "completeness", "tool_calls", "correctness")


def _variant() -> str:
    return os.getenv("EVAL_VARIANT", "baseline").strip() or "baseline"


async def _evaluate_one(
    backend: str, model_name: str, variant: str, max_concurrency: int,
    client: Client, dataset_id: str,
) -> dict:
    print(f"\n=== {backend}:{model_name} [{variant}] ===", flush=True)
    prefix = f"{_experiment_prefix(backend, model_name)}-{variant}"
    n = len(BENCHMARK_EXAMPLES_V4)

    if os.getenv("EVAL_FORCE_RERUN", "").strip() not in ("", "0", "false", "False"):
        existing = None
    else:
        existing = _find_completed_experiment(client, dataset_id, prefix, expected_examples=n)
    if existing:
        print(f"  SKIP — already completed: {existing}", flush=True)
        return {"skipped": True, "quota_exhausted": False, "experiment": existing}

    agent = await create_netbox_agent(backend=backend, model_name=model_name)
    try:
        results = await aevaluate(
            _build_target(agent),
            data=DATASET_NAME_V4,
            evaluators=ALL_EVALUATORS,
            experiment_prefix=prefix,
            max_concurrency=max_concurrency,
            metadata={"backend": backend, "model": model_name,
                      "dataset": DATASET_NAME_V4, "variant": variant},
        )
        print(f"  experiment: {results.experiment_name}", flush=True)
        quota_dead = _experiment_was_quota_throttled(client, results.experiment_name, n)
        if quota_dead:
            print("  QUOTA EXHAUSTED — most runs 429'd. Aborting.", flush=True)
        return {"skipped": False, "quota_exhausted": quota_dead,
                "experiment": results.experiment_name}
    finally:
        await agent.cleanup()


def _mean(xs):
    return round(sum(xs) / len(xs), 3) if xs else None


def _leaderboard(client: Client, experiment_names: list[str]) -> list[dict]:
    rows = []
    for name in experiment_names:
        runs = list(client.list_runs(project_name=name, is_root=True))
        agg = {k: [] for k in _SCORE_KEYS}
        per_q = []
        for r in runs:
            fb = _fetch_feedback(client, r)
            for k in _SCORE_KEYS:
                if fb.get(k) is not None:
                    agg[k].append(fb[k])
            per_q.append({
                "question": (r.inputs or {}).get("question", "")[:55],
                **{k: fb.get(k) for k in _SCORE_KEYS},
                "error": bool(getattr(r, "error", None)),
            })
        rows.append({
            "experiment": name,
            "n_runs": len(runs),
            "n_errors": sum(1 for r in runs if getattr(r, "error", None)),
            **{f"{k}_mean": _mean(agg[k]) for k in _SCORE_KEYS},
            "per_question": per_q,
        })
    # Rank by CORRECTNESS first (the fix), then completeness, then fewer tool calls.
    rows.sort(key=lambda r: (
        -(r["correctness_mean"] or 0),
        -(r["completeness_mean"] or 0),
        (r["tool_calls_mean"] or 1e9),
    ))
    return rows


def _write_records(rows: list[dict], variant: str, stamp: str) -> Path:
    _TRACES_DIR.mkdir(parents=True, exist_ok=True)
    path = _TRACES_DIR / f"{stamp[:10]}_netbox-benchmark-v4_{variant}.md"
    lines = [
        f"# netbox-benchmark-v4 [{variant}] — {stamp}",
        "",
        f"- Dataset: **{DATASET_NAME_V4}** ({len(BENCHMARK_EXAMPLES_V4)} examples)",
        f"- Variant: **{variant}** (baseline = no GraphQL tool; graphql = GraphQL tool wired in)",
        "- Evaluators: entity_coverage · completeness · tool_calls · **correctness** (reference-grounded)",
        "",
        "## Leaderboard (ranked by correctness ↓)",
        "",
        "| # | Model (experiment) | correctness | completeness | entity_cov | tool_calls | errors |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows, 1):
        lines.append(
            f"| {i} | `{r['experiment']}` | {r['correctness_mean']} | "
            f"{r['completeness_mean']} | {r['entity_coverage_mean']} | "
            f"{r['tool_calls_mean']} | {r['n_errors']} |"
        )
    lines += ["", "## Per-question detail", ""]
    for r in rows:
        lines.append(f"### `{r['experiment']}`")
        lines.append("")
        lines.append("| question | correctness | completeness | entity_cov | tool_calls | err |")
        lines.append("|---|---|---|---|---|---|")
        for q in r["per_question"]:
            lines.append(
                f"| {q['question']} | {q['correctness']} | {q['completeness']} | "
                f"{q['entity_coverage']} | {q['tool_calls']} | {'✗' if q['error'] else ''} |"
            )
        lines.append("")
    path.write_text("\n".join(lines))
    return path


async def main() -> None:
    variant = _variant()
    dataset = ensure_dataset_v4()
    client = Client()
    models = _parse_models_env() or _DEFAULT_V4_MODELS
    max_concurrency = int(os.getenv("EVAL_MAX_CONCURRENCY", "1"))

    print(f"v4 A/B [{variant}]: {len(models)} model(s) × {DATASET_NAME_V4}", flush=True)
    for b, m in models:
        print(f"  - {b}:{m}", flush=True)

    experiment_names, aborted = [], False
    for backend, model in models:
        try:
            res = await _evaluate_one(
                backend, model, variant, max_concurrency, client, str(dataset.id)
            )
            if res.get("experiment"):
                experiment_names.append(res["experiment"])
            if res.get("quota_exhausted"):
                aborted = True
                break
        except Exception as e:
            print(f"  FAILED {backend}:{model}: {type(e).__name__}: {e}", flush=True)

    if experiment_names:
        stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        rows = _leaderboard(client, experiment_names)
        path = _write_records(rows, variant, stamp)
        print(f"\nRecorded [{variant}] -> {path}", flush=True)
        for i, r in enumerate(rows, 1):
            print(f"  {i}. {r['experiment']}: corr={r['correctness_mean']} "
                  f"comp={r['completeness_mean']} tools={r['tool_calls_mean']}", flush=True)
    if aborted:
        print("\nAborted on quota — re-run after the Ollama Cloud limit resets.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
