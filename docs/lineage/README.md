# Lineage — Harvested from the ancestor `deepagents` repo

This directory preserves the genuinely-valuable design rationale and empirical findings from
**[FinnMacCumail/deepagents](https://github.com/FinnMacCumail/deepagents)** — the older NetBox
agent (vendored DeepAgents 0.0.5, Anthropic-cloud-only) that `ollamaDeepAgents` evolved from.

These documents predate this project but their conclusions carried forward and justify current
design choices. They were harvested 2026-06-22 as part of the three-repo update documented in
`../development/2026-06-22_multi-repo-update-plan.md`.

| File | Source | Why preserved |
|---|---|---|
| [context-engineering.md](context-engineering.md) | `docs/guides/context-engineering-report.md` | Citation-backed synthesis of the five context strategies (Offload / Reduce / Retrieve / Isolate / Cache). The "generic > specialized tools" and "no subagents" findings are still the design. |
| [no-subagents-rationale.md](no-subagents-rationale.md) | `examples/netbox/docs/netbox/reports/NO_SUBAGENTS_RATIONALE.md` | Empirical justification for subagents-off — corroborated by the 2026-06 QuickJS PTC spikes. |
| [tool-removal-results.md](tool-removal-results.md) | `examples/netbox/docs/netbox/analysis/TOOL_REMOVAL_RESULTS.md` | Empirical results behind reducing 62 specialized tools → a handful of generic ones. |
| [validation-results-summary.md](validation-results-summary.md) | `examples/netbox/docs/netbox/analysis/VALIDATION_RESULTS_SUMMARY.md` | Validation findings from the ancestor build. |

Also harvested elsewhere in this repo:
- **Trace-analysis scripts** → `tests/manual/legacy-trace-tools/` (precursors to the
  `tests/eval/` model-matrix harness — the observability lineage).
- **PRP methodology** → `.claude/commands/{generate,execute}-prp.md` + `PRPs/templates/prp_base.md`
  (the "Product Requirement Prompt" planning workflow).

> These are **historical/reference** material. For current architecture and practice see
> `CLAUDE.md`, `AGENTS.md`, and `docs/reference/`.
