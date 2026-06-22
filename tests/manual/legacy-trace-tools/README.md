# Legacy trace-analysis scripts (harvested)

Harvested 2026-06-22 from the ancestor repo **FinnMacCumail/deepagents**
(`examples/netbox/analysis_tools/`). These are the hand-rolled LangSmith trace-analysis
scripts used on the older NetBox agent — the **precursors to the `tests/eval/` model-matrix
evaluation harness** in this repo.

They are kept for lineage and occasional ad-hoc trace inspection. They are **not** part of the
current evaluation workflow — use `tests/eval/run_matrix.py` for systematic, scored evaluation.

| Script | Purpose (as built for the ancestor agent) |
|---|---|
| `analyze_traces_compact.py` | Compact summary of a LangSmith trace |
| `detailed_trace_analysis.py` | Full per-step trace breakdown |
| `compare_traces.py` | Diff two traces side by side |
| `compare_tool_removal.py` | Before/after analysis of the 62→generic tool reduction |
| `investigate_query2_regression.py` | One-off regression investigation |
| `analyze_validation_traces.py`, `analyze_validation_manual.py` | Validation-suite trace analysis |

> Caveat: these target the ancestor's Anthropic-only setup and its LangSmith project layout;
> they may need adapting (model names, project names, env) before running against this repo's
> traces. The `tests/eval/` harness is the maintained path.
