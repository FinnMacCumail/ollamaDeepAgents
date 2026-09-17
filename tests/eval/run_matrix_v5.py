"""Run the netbox-benchmark-v5 stratified dataset across the model matrix.

Same machinery as run_matrix_v4, with three differences that matter:

  - Dataset: netbox-benchmark-v5, loaded via `ensure_dataset_v5()`, which SYNCS
    (add/update/delete). v3/v4's loaders are create-only, so editing their
    Python file had no effect once the dataset existed. Edit dataset_v5.py and
    the next run picks the change up.

  - **Per-tier breakdown (authoring-plan Fix 3).** v4 reports a single
    `tool_calls_mean` over the whole set. v5 items are stratified simple /
    medium / advanced, and the advanced tier has a higher tool-call floor BY
    DESIGN, so one global number penalises it by construction and hides which
    tier a model actually fails. Every score is additionally broken out by
    difficulty, and tool calls are reported against the tier's budget.

  - Default scope is a SINGLE model (smoke run). The v5 set is ~6x the size of
    v4, so a full 10-model matrix is a real quota spend; opt into it explicitly
    with EVAL_MODELS.

`_fetch_feedback` is imported from run_matrix_v3 rather than reimplemented: it
derives the expected feedback count from ALL_EVALUATORS, so it cannot return
before `correctness` — the primary metric — has landed.

Usage:
    # smoke run, one model, whatever is currently in dataset_v5.py
    ./venv/bin/python -m tests.eval.run_matrix_v5

    # wider sweep (see the MODEL AVAILABILITY note at the foot of this file --
    # glm-5:cloud and gemini-3-flash-preview:cloud are RETIRED and return 410)
    EVAL_MODELS="ollama:deepseek-v4-pro:cloud,ollama:qwen3.5:397b-cloud" \
        ./venv/bin/python -m tests.eval.run_matrix_v5

    EVAL_FORCE_RERUN=1 ./venv/bin/python -m tests.eval.run_matrix_v5
"""

from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from langsmith import Client, aevaluate

from src.agents.netbox_agent import create_netbox_agent
from tests.eval.dataset_v5 import (
    BENCHMARK_EXAMPLES_V5,
    DATASET_NAME_V5,
    DIFFICULTIES,
    TOOL_CALL_BUDGET,
    ensure_dataset_v5,
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

# Smoke-run default: ONE model. Override with EVAL_MODELS for a real sweep.
_DEFAULT_V5_MODELS: list[tuple[str, str]] = [
    ("ollama", "deepseek-v4-flash:cloud"),
]

_TRACES_DIR = Path(__file__).resolve().parents[2] / "docs" / "traces"
_SCORE_KEYS = ("entity_coverage", "completeness", "tool_calls", "correctness")


def _variant() -> str:
    return os.getenv("EVAL_VARIANT", "baseline").strip() or "baseline"


def _tier_of(question: str) -> str:
    """Map a run back to its authored tier. Runs carry inputs, not outputs."""
    for ex in BENCHMARK_EXAMPLES_V5:
        if ex.question == question:
            return ex.difficulty
    return "unknown"


async def _evaluate_one(
    backend: str, model_name: str, variant: str, max_concurrency: int,
    client: Client, dataset_id: str,
) -> dict:
    print(f"\n=== {backend}:{model_name} [{variant}] ===", flush=True)
    prefix = f"{_experiment_prefix(backend, model_name)}-v5-{variant}"
    n = len(BENCHMARK_EXAMPLES_V5)

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
            data=DATASET_NAME_V5,
            evaluators=ALL_EVALUATORS,
            experiment_prefix=prefix,
            max_concurrency=max_concurrency,
            metadata={"backend": backend, "model": model_name,
                      "dataset": DATASET_NAME_V5, "variant": variant},
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
        by_tier: dict[str, dict[str, list]] = defaultdict(lambda: {k: [] for k in _SCORE_KEYS})
        per_q = []
        for r in runs:
            fb = _fetch_feedback(client, r)
            q = (r.inputs or {}).get("question", "")
            tier = _tier_of(q)
            for k in _SCORE_KEYS:
                if fb.get(k) is not None:
                    agg[k].append(fb[k])
                    by_tier[tier][k].append(fb[k])
            per_q.append({
                "question": q[:55],
                "tier": tier,
                **{k: fb.get(k) for k in _SCORE_KEYS},
                "over_budget": (
                    fb.get("tool_calls") is not None
                    and fb["tool_calls"] > TOOL_CALL_BUDGET.get(tier, 1e9)
                ),
                "error": bool(getattr(r, "error", None)),
            })
        rows.append({
            "experiment": name,
            "n_runs": len(runs),
            "n_errors": sum(1 for r in runs if getattr(r, "error", None)),
            **{f"{k}_mean": _mean(agg[k]) for k in _SCORE_KEYS},
            "tiers": {
                t: {f"{k}_mean": _mean(by_tier[t][k]) for k in _SCORE_KEYS}
                   | {"n": len(by_tier[t]["correctness"]) or len(by_tier[t]["entity_coverage"])}
                for t in DIFFICULTIES if t in by_tier
            },
            "per_question": per_q,
        })
    rows.sort(key=lambda r: (
        -(r["correctness_mean"] or 0),
        -(r["completeness_mean"] or 0),
        (r["tool_calls_mean"] or 1e9),
    ))
    return rows


def _write_records(rows: list[dict], variant: str, stamp: str) -> Path:
    _TRACES_DIR.mkdir(parents=True, exist_ok=True)
    path = _TRACES_DIR / f"{stamp[:10]}_netbox-benchmark-v5_{variant}.md"
    lines = [
        f"# netbox-benchmark-v5 [{variant}] — {stamp}",
        "",
        f"- Dataset: **{DATASET_NAME_V5}** ({len(BENCHMARK_EXAMPLES_V5)} examples)",
        "- Evaluators: entity_coverage · completeness · tool_calls · **correctness**",
        f"- Tool-call budgets: {', '.join(f'{t}≤{b}' for t, b in TOOL_CALL_BUDGET.items())}",
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

    lines += ["", "## Per-tier breakdown", "",
              "A single global tool_calls figure penalises the advanced tier by "
              "construction — it has a higher floor by design.", ""]
    for r in rows:
        lines.append(f"### `{r['experiment']}`")
        lines.append("")
        lines.append("| tier | n | correctness | completeness | entity_cov | tool_calls | budget |")
        lines.append("|---|---|---|---|---|---|---|")
        for t, s in r["tiers"].items():
            lines.append(
                f"| {t} | {s['n']} | {s['correctness_mean']} | {s['completeness_mean']} | "
                f"{s['entity_coverage_mean']} | {s['tool_calls_mean']} | "
                f"≤{TOOL_CALL_BUDGET.get(t, '—')} |"
            )
        lines.append("")

    lines += ["## Per-question detail", ""]
    for r in rows:
        lines.append(f"### `{r['experiment']}`")
        lines.append("")
        lines.append("| question | tier | correctness | completeness | entity_cov | tool_calls | over | err |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for q in r["per_question"]:
            lines.append(
                f"| {q['question']} | {q['tier']} | {q['correctness']} | "
                f"{q['completeness']} | {q['entity_coverage']} | {q['tool_calls']} | "
                f"{'⚠' if q['over_budget'] else ''} | {'✗' if q['error'] else ''} |"
            )
        lines.append("")
    path.write_text("\n".join(lines))
    return path


async def main() -> None:
    variant = _variant()
    dataset = ensure_dataset_v5()
    client = Client()
    models = _parse_models_env() or _DEFAULT_V5_MODELS
    max_concurrency = int(os.getenv("EVAL_MAX_CONCURRENCY", "1"))

    print(f"v5 [{variant}]: {len(models)} model(s) × {DATASET_NAME_V5} "
          f"({len(BENCHMARK_EXAMPLES_V5)} examples)", flush=True)
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
            for t, s in r["tiers"].items():
                print(f"       {t:<9} n={s['n']:<3} corr={s['correctness_mean']} "
                      f"tools={s['tool_calls_mean']} (budget ≤{TOOL_CALL_BUDGET.get(t)})",
                      flush=True)
    if aborted:
        print("\nAborted on quota — re-run after the Ollama Cloud limit resets.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())


# ---------------------------------------------------------------------------
# MODEL AVAILABILITY (measured 2026-09-17)
#
# `ollama list` is NOT a reliable guide for :cloud models. It still lists
# entries whose cloud endpoint has been retired, and the run only discovers
# this when the first example executes -- 40 minutes into a 90-item sweep.
# Preflight any new model with a one-token invoke before committing a run.
#
#   RETIRED (HTTP 410, both retired 2026-07-15):
#     glm-5:cloud
#     gemini-3-flash-preview:cloud
#
#   ALIVE:
#     deepseek-v4-flash:cloud, deepseek-v4-pro:cloud
#     qwen3.5:397b-cloud, kimi-k2.6:cloud, minimax-m3:cloud
#     nemotron-3-ultra:cloud, nemotron-3-super:cloud
#
# Note gpt-oss:120b-cloud is deliberately NOT used as a subject model: the
# judge is gpt-oss:20b, so scoring it would be same-family self-judgement,
# the bias evaluators.py's docstring warns about.
# ---------------------------------------------------------------------------
