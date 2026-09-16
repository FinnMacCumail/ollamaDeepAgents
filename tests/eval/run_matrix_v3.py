"""Run the netbox-benchmark-v3 cross-domain dataset across the model matrix.

Same design as run_matrix.py (one DeepAgent per (backend, model), each model's
runs grouped under its own LangSmith experiment_prefix), but targets the v3
cross-domain dataset and reuses run_matrix's building blocks (target wrapper,
skip-completed, quota-abort) and evaluators.ALL_EVALUATORS unchanged.

Differences from v2 runner:
  - Dataset: netbox-benchmark-v3 (6 cross-domain examples, ensure_dataset_v3).
  - Model list: run_matrix.DEFAULT_MODELS minus any excluded model. By default
    excludes `gemini-3-flash` (per the run request). Override the exclusion with
    EVAL_EXCLUDE="substr,substr" or the whole set with EVAL_MODELS.
  - After the matrix, writes a leaderboard markdown + raw per-run JSONL under
    docs/traces/ so the run is recorded in-repo.

Usage:
    python -m tests.eval.run_matrix_v3
    EVAL_EXCLUDE="gemini,minimax" python -m tests.eval.run_matrix_v3
    EVAL_FORCE_RERUN=1 python -m tests.eval.run_matrix_v3
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from langsmith import Client, aevaluate

from src.agents.netbox_agent import create_netbox_agent
from tests.eval.dataset_v3 import (
    BENCHMARK_EXAMPLES_V3,
    DATASET_NAME_V3,
    ensure_dataset_v3,
)
from tests.eval.evaluators import ALL_EVALUATORS
from tests.eval.run_matrix import (
    DEFAULT_MODELS,
    _build_target,
    _experiment_prefix,
    _experiment_was_quota_throttled,
    _find_completed_experiment,
)

# Default exclusion for this run: the Google Gemini flash preview.
_DEFAULT_EXCLUDE = ("gemini-3-flash",)

_TRACES_DIR = Path(__file__).resolve().parents[2] / "docs" / "traces"


def _select_models() -> list[tuple[str, str]]:
    """DEFAULT_MODELS (or EVAL_MODELS) minus excluded substrings."""
    from tests.eval.run_matrix import _parse_models_env

    base = _parse_models_env() or list(DEFAULT_MODELS)
    raw_excl = os.getenv("EVAL_EXCLUDE")
    excludes = (
        [s.strip() for s in raw_excl.split(",") if s.strip()]
        if raw_excl is not None
        else list(_DEFAULT_EXCLUDE)
    )
    kept, dropped = [], []
    for backend, model in base:
        if any(sub in model for sub in excludes):
            dropped.append(f"{backend}:{model}")
        else:
            kept.append((backend, model))
    if dropped:
        print(f"Excluding {len(dropped)} model(s): {', '.join(dropped)}", flush=True)
    return kept


async def _evaluate_one_v3(
    backend: str,
    model_name: str,
    max_concurrency: int,
    client: Client,
    dataset_id: str,
) -> dict:
    """Run one model against v3; return {'skipped', 'quota_exhausted', 'experiment'}."""
    print(f"\n=== {backend}:{model_name} ===", flush=True)
    prefix = _experiment_prefix(backend, model_name)
    n_examples = len(BENCHMARK_EXAMPLES_V3)

    if os.getenv("EVAL_FORCE_RERUN", "").strip() not in ("", "0", "false", "False"):
        existing = None
    else:
        existing = _find_completed_experiment(
            client, dataset_id, prefix, expected_examples=n_examples
        )
    if existing:
        print(f"  SKIP — already completed: {existing}", flush=True)
        return {"skipped": True, "quota_exhausted": False, "experiment": existing}

    agent = await create_netbox_agent(backend=backend, model_name=model_name)
    try:
        results = await aevaluate(
            _build_target(agent),
            data=DATASET_NAME_V3,
            evaluators=ALL_EVALUATORS,
            experiment_prefix=prefix,
            max_concurrency=max_concurrency,
            metadata={"backend": backend, "model": model_name, "dataset": DATASET_NAME_V3},
        )
        print(f"  experiment: {results.experiment_name}", flush=True)
        quota_dead = _experiment_was_quota_throttled(
            client, results.experiment_name, n_examples
        )
        if quota_dead:
            print("  QUOTA EXHAUSTED — most runs 429'd. Aborting matrix.", flush=True)
        return {
            "skipped": False,
            "quota_exhausted": quota_dead,
            "experiment": results.experiment_name,
        }
    finally:
        await agent.cleanup()


def _fetch_feedback(client: Client, run) -> dict:
    """Read a run's feedback, retrying while ingestion lags.

    LangSmith feedback is written asynchronously; a run that finishes slowly
    (e.g. a tool-retry storm) can have its outputs persisted before every
    evaluator score propagates. Retry until all of them are present (or the run
    errored, in which case partial/empty feedback is expected and final).

    NB: this used to break at a hard-coded `len(fb) >= 3`, which predates the
    reference-grounded `correctness_judge`. With four evaluators that could
    return as soon as entity_coverage/completeness/tool_calls landed, silently
    dropping `correctness` -- the PRIMARY metric -- to None. The expected count
    is now derived from ALL_EVALUATORS so adding an evaluator cannot
    reintroduce the bug.
    """
    retries = int(os.getenv("EVAL_FEEDBACK_RETRIES", "5"))
    delay = float(os.getenv("EVAL_FEEDBACK_DELAY", "6"))
    expected = len(ALL_EVALUATORS)
    errored = bool(getattr(run, "error", None))
    fb: dict = {}
    for attempt in range(retries):
        fb = {f.key: f.score for f in client.list_feedback(run_ids=[run.id])}
        if errored or len(fb) >= expected:
            break
        if attempt < retries - 1:
            time.sleep(delay)
    return fb


def _leaderboard(client: Client, experiment_names: list[str]) -> list[dict]:
    """Aggregate per-experiment feedback scores into leaderboard rows."""
    rows = []
    for name in experiment_names:
        runs = list(client.list_runs(project_name=name, is_root=True))
        n_err = sum(1 for r in runs if getattr(r, "error", None))
        agg: dict[str, list[float]] = {"entity_coverage": [], "completeness": [], "tool_calls": []}
        per_q = []
        for r in runs:
            fb = _fetch_feedback(client, r)
            for k in agg:
                if fb.get(k) is not None:
                    agg[k].append(fb[k])
            q = (r.inputs or {}).get("question", "")
            per_q.append({
                "question": q[:60],
                "entity_coverage": fb.get("entity_coverage"),
                "completeness": fb.get("completeness"),
                "tool_calls": fb.get("tool_calls"),
                "error": bool(getattr(r, "error", None)),
            })

        def _mean(xs):
            return round(sum(xs) / len(xs), 3) if xs else None

        rows.append({
            "experiment": name,
            "n_runs": len(runs),
            "n_errors": n_err,
            "entity_coverage_mean": _mean(agg["entity_coverage"]),
            "completeness_mean": _mean(agg["completeness"]),
            "tool_calls_mean": _mean(agg["tool_calls"]),
            "per_question": per_q,
        })
    # Sort by (completeness, entity_coverage) desc, then tool_calls asc.
    rows.sort(
        key=lambda r: (
            -(r["completeness_mean"] or 0),
            -(r["entity_coverage_mean"] or 0),
            (r["tool_calls_mean"] or 1e9),
        )
    )
    return rows


def _write_records(client: Client, dataset_id: str, rows: list[dict], stamp: str) -> Path:
    """Write leaderboard markdown + raw per-run JSONL under docs/traces/."""
    _TRACES_DIR.mkdir(parents=True, exist_ok=True)
    md_path = _TRACES_DIR / f"{stamp[:10]}_netbox-benchmark-v3_matrix.md"

    lines = [
        f"# netbox-benchmark-v3 model-matrix run — {stamp}",
        "",
        f"- Dataset: **{DATASET_NAME_V3}** ({len(BENCHMARK_EXAMPLES_V3)} cross-domain examples)",
        f"- Evaluators: entity_coverage (code) · completeness (LLM-judge, "
        f"{os.getenv('EVAL_JUDGE_MODEL', 'gpt-oss:20b')}) · tool_calls (trajectory)",
        f"- Models: {len(rows)} (gemini-3-flash excluded)",
        "",
        "## Leaderboard",
        "",
        "Sorted by completeness ↓, then entity_coverage ↓, then tool_calls ↑.",
        "",
        "| # | Model (experiment) | entity_cov | completeness | tool_calls | runs | errors |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows, 1):
        lines.append(
            f"| {i} | `{r['experiment']}` | {r['entity_coverage_mean']} | "
            f"{r['completeness_mean']} | {r['tool_calls_mean']} | "
            f"{r['n_runs']} | {r['n_errors']} |"
        )
    lines += ["", "## Per-question detail", ""]
    for r in rows:
        lines.append(f"### `{r['experiment']}`")
        lines.append("")
        lines.append("| question | entity_cov | completeness | tool_calls | err |")
        lines.append("|---|---|---|---|---|")
        for q in r["per_question"]:
            lines.append(
                f"| {q['question']} | {q['entity_coverage']} | {q['completeness']} | "
                f"{q['tool_calls']} | {'✗' if q['error'] else ''} |"
            )
        lines.append("")
    md_path.write_text("\n".join(lines))

    # Raw per-run export (inputs/outputs/feedback) for reproducibility.
    raw_dir = _TRACES_DIR / f"raw_{stamp[:10]}_netbox-benchmark-v3"
    raw_dir.mkdir(exist_ok=True)
    for r in rows:
        runs = list(client.list_runs(project_name=r["experiment"], is_root=True))
        recs = []
        for run in runs:
            fb = _fetch_feedback(client, run)
            recs.append({
                "experiment": r["experiment"],
                "inputs": run.inputs,
                "outputs": run.outputs,
                "error": getattr(run, "error", None),
                "feedback": fb,
            })
        (raw_dir / f"{r['experiment']}.jsonl").write_text(
            "\n".join(json.dumps(x, default=str) for x in recs)
        )
    return md_path


async def main() -> None:
    dataset = ensure_dataset_v3()
    client = Client()
    models = _select_models()
    max_concurrency = int(os.getenv("EVAL_MAX_CONCURRENCY", "1"))

    print(f"Matrix: {len(models)} model(s) × {DATASET_NAME_V3}", flush=True)
    for backend, model in models:
        print(f"  - {backend}:{model}", flush=True)

    experiment_names: list[str] = []
    aborted = False
    for backend, model in models:
        try:
            result = await _evaluate_one_v3(
                backend, model, max_concurrency, client, str(dataset.id)
            )
            if result.get("experiment"):
                experiment_names.append(result["experiment"])
            if result.get("quota_exhausted"):
                aborted = True
                remaining = [f"{b}:{m}" for b, m in models[models.index((backend, model)) + 1:]]
                if remaining:
                    print(f"\nSkipping {len(remaining)} remaining (quota): "
                          f"{', '.join(remaining)}", flush=True)
                break
        except Exception as e:
            print(f"  FAILED {backend}:{model}: {type(e).__name__}: {e}", flush=True)

    if experiment_names:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        rows = _leaderboard(client, experiment_names)
        md_path = _write_records(client, str(dataset.id), rows, stamp)
        print(f"\nRecorded run -> {md_path}", flush=True)
        print("\nLeaderboard (completeness ↓):", flush=True)
        for i, r in enumerate(rows, 1):
            print(f"  {i}. {r['experiment']}: comp={r['completeness_mean']} "
                  f"ent={r['entity_coverage_mean']} tools={r['tool_calls_mean']} "
                  f"err={r['n_errors']}", flush=True)
    if aborted:
        print("\nMatrix aborted on quota — re-run after the Ollama Cloud session "
              "limit resets; skip-completed picks up the rest.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
