"""Re-score the stored netbox-benchmark-v3 answers with the reference-grounded
`correctness_judge` (no agent reruns — only judge calls over answers already in
LangSmith).

Motivation: v3's evaluators never read `reference_answer`, so a confidently
hallucinated "~7.7% IP utilization" answer scored 0.9 on completeness. This
script fact-checks each stored answer against the verified reference, pushes a
new `correctness` feedback key onto each run (additive; the v3 experiments are
otherwise untouched), and writes a before/after scorecard to docs/traces/.

Usage:
    ./venv/bin/python -m tests.eval.rescore_v4
    RESCORE_PUSH_FEEDBACK=0 ./venv/bin/python -m tests.eval.rescore_v4   # scorecard only
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from langsmith import Client

load_dotenv()

from tests.eval.dataset_v4 import BENCHMARK_EXAMPLES_V4  # noqa: E402
from tests.eval.evaluators import correctness_judge  # noqa: E402

V3_DATASET_ID = "2185e223-186f-4296-a1d7-55015984f7b5"
_TRACES_DIR = Path(__file__).resolve().parents[2] / "docs" / "traces"
_PUSH = os.getenv("RESCORE_PUSH_FEEDBACK", "1") not in ("0", "false", "False")

# question -> reference facts
_REF = {
    ex.question: {
        "reference_answer": ex.reference_answer,
        "expected_entities": list(ex.expected_entities),
        "category": ex.category,
    }
    for ex in BENCHMARK_EXAMPLES_V4
}


def _short(model_experiment: str) -> str:
    # ollama-deepseek-v4-flash-cloud-07b5f223 -> deepseek-v4-flash
    name = model_experiment
    for pre in ("ollama-",):
        if name.startswith(pre):
            name = name[len(pre):]
    # drop the trailing 8-hex experiment suffix
    parts = name.rsplit("-", 1)
    if len(parts) == 2 and len(parts[1]) == 8:
        name = parts[0]
    return name.replace("-cloud", "")


def main() -> None:
    client = Client()
    experiments = [
        p.name for p in client.list_projects(reference_dataset_id=V3_DATASET_ID)
    ]
    print(f"Re-scoring {len(experiments)} v3 experiments...", flush=True)

    rows = []  # (model, question, category, old_completeness, old_entity, new_correctness, rationale, errored)
    per_model = defaultdict(lambda: {"comp": [], "corr": []})

    for exp in experiments:
        model = _short(exp)
        runs = list(client.list_runs(project_name=exp, is_root=True))
        for r in runs:
            q = (r.inputs or {}).get("question", "")
            ref = _REF.get(q)
            if ref is None:
                continue
            answer = (r.outputs or {}).get("answer", "") if r.outputs else ""
            errored = bool(getattr(r, "error", None))
            fb = {f.key: f.score for f in client.list_feedback(run_ids=[r.id])}
            old_comp = fb.get("completeness")
            old_ent = fb.get("entity_coverage")

            res = correctness_judge(
                inputs={"question": q},
                outputs={"answer": answer},
                reference_outputs=ref,
            )
            new_corr = res["score"]
            rationale = res.get("comment", "")

            if _PUSH and new_corr is not None:
                try:
                    client.create_feedback(
                        run_id=r.id, key="correctness", score=new_corr, comment=rationale
                    )
                except Exception as e:  # noqa: BLE001
                    print(f"  (feedback push failed for {model}/{q[:30]}: {e})", flush=True)

            rows.append(
                (model, q, ref["category"], old_comp, old_ent, new_corr, rationale, errored)
            )
            if old_comp is not None:
                per_model[model]["comp"].append(old_comp)
            if new_corr is not None:
                per_model[model]["corr"].append(new_corr)
        print(f"  scored {model}", flush=True)

    _write(rows, per_model)


def _mean(xs):
    return round(sum(xs) / len(xs), 3) if xs else None


def _write(rows, per_model):
    _TRACES_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    path = _TRACES_DIR / "2026-07-20_netbox-benchmark-v4-rescore.md"

    # per-model summary sorted by new correctness
    summary = sorted(
        per_model.items(),
        key=lambda kv: -(_mean(kv[1]["corr"]) or 0),
    )

    lines = [
        f"# netbox-benchmark-v4 re-score of the v3 answers — {stamp}",
        "",
        "Re-scoring the **stored 2026-07-05 v3 answers** (no agent reruns) with the new "
        "reference-grounded `correctness_judge`, which reads `reference_answer` and flags "
        "factual contradictions. v3's evaluators never read the reference, so completeness "
        "over-rewarded confident hallucinations. Ground truth re-verified vs live NetBox "
        "2026-07-20 (DM Data prefix 10.112.149.0/24 = 0 IPs; all 180 NetBox IPs are in "
        "172.16.0.0/24 → 0% allocation).",
        "",
        "## Per-model: old completeness vs new correctness (mean over 6 questions)",
        "",
        "| Model | old completeness | new correctness | Δ |",
        "|---|---|---|---|",
    ]
    for model, agg in summary:
        c_old, c_new = _mean(agg["comp"]), _mean(agg["corr"])
        delta = round((c_new or 0) - (c_old or 0), 3) if (c_old is not None and c_new is not None) else None
        lines.append(f"| `{model}` | {c_old} | {c_new} | {delta} |")

    lines += [
        "",
        "## False positives — high completeness, low correctness",
        "",
        "Rows where the old pipeline scored the answer complete (≥0.7) but it factually "
        "contradicts the verified reference (correctness ≤0.5). These are the hallucinations "
        "the v3 harness could not see.",
        "",
        "| Model | category | old comp | new corr | contradiction |",
        "|---|---|---|---|---|",
    ]
    fps = [
        r for r in rows
        if r[3] is not None and r[3] >= 0.7 and r[5] is not None and r[5] <= 0.5
    ]
    fps.sort(key=lambda r: (r[3] or 0) - (r[5] or 0), reverse=True)
    for model, _q, cat, old_comp, _old_ent, new_corr, rationale, _err in fps:
        lines.append(f"| `{model}` | {cat} | {old_comp} | {new_corr} | {rationale[:90]} |")
    if not fps:
        lines.append("| — | — | — | — | (none) |")

    lines += ["", "## Full per-question detail", ""]
    by_model = defaultdict(list)
    for r in rows:
        by_model[r[0]].append(r)
    for model in [m for m, _ in summary]:
        lines.append(f"### `{model}`")
        lines.append("")
        lines.append("| category | old comp | old entity | new correctness | note |")
        lines.append("|---|---|---|---|---|")
        for _, _q, cat, old_comp, old_ent, new_corr, rationale, err in by_model[model]:
            note = ("ERROR " if err else "") + (rationale[:80] if rationale else "")
            lines.append(f"| {cat} | {old_comp} | {old_ent} | {new_corr} | {note} |")
        lines.append("")

    path.write_text("\n".join(lines))
    print(f"\nWrote {path}", flush=True)
    print("\nPer-model (old completeness -> new correctness):", flush=True)
    for model, agg in summary:
        print(f"  {model}: {_mean(agg['comp'])} -> {_mean(agg['corr'])}", flush=True)
    print(f"\nFalse positives (high completeness, low correctness): {len(fps)}", flush=True)


if __name__ == "__main__":
    main()
