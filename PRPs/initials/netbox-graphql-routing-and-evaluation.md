# FEATURE

Teach the NetBox DeepAgent **when** to choose `netbox_graphql` (from PRP 1)
instead of the existing MCP tools, and determine **empirically** whether GraphQL
improves cross-domain queries without regressing simple ones.

Two deliverables:
1. a new progressive-disclosure skill that encodes the routing policy;
2. an A/B evaluation on the **existing** `netbox-benchmark-v3` harness comparing
   GraphQL-enabled vs. MCP-only, extended with the metric axes not yet captured.

> **Depends on PRP 1** (`netbox-graphql-read-tool.md`) being merged and green.
> Do not start until `netbox_graphql` executes real nested queries.

# CRITICAL — REUSE, DO NOT RE-CREATE, THE v3 HARNESS

`netbox-benchmark-v3` **already exists** and is committed (`d8f478f`,
2026-07-05). Do not create a new dataset. The relevant assets:

- `tests/eval/dataset_v3.py` — `DATASET_NAME_V3 = "netbox-benchmark-v3"`,
  `BENCHMARK_EXAMPLES_V3` (6 verified cross-domain examples, incl. two
  negative-finding tests), `ensure_dataset_v3()` (idempotent). LangSmith dataset
  already populated.
- `tests/eval/run_matrix_v3.py` — the model-matrix runner. Reuses
  `evaluators.ALL_EVALUATORS`, supports `EVAL_MODELS` / `EVAL_EXCLUDE` /
  `EVAL_FORCE_RERUN`, writes a leaderboard + raw JSONL to `docs/traces/`.
- `tests/eval/evaluators.py` — `ALL_EVALUATORS = [entity_coverage,
  completeness_judge, tool_call_efficiency]`. **3 of the 7 target metrics already
  exist here.**
- Baseline already recorded: `docs/traces/2026-07-05_netbox-benchmark-v3_matrix.md`
  (9-model MCP-only run). **This is the MCP-only baseline to A/B against.**

The 6 existing examples ARE cross-domain. Only if they don't sufficiently
exercise deep nested-relationship retrieval, PRP 2 MAY append 2–3 nested cases —
but adding examples changes the dataset for prior experiments, so prefer keeping
the 6 stable for comparability and, if needed, spin a small labelled supplement
rather than mutating v3. The generated PRP decides.

# METRICS — EXTEND EXISTING INFRA, DO NOT REINVENT

Target comparison axes (7). Note what already exists so the PRP extends rather
than rebuilds:

| Metric | Status |
|---|---|
| answer completeness | ✅ `completeness_judge` (evaluators.py) |
| entity coverage | ✅ `entity_coverage` (evaluators.py) |
| outer tool-call count | ✅ `tool_call_efficiency` (evaluators.py) |
| total wall time | ➕ NEW — capture per-run |
| model tokens | ➕ NEW — capture per-run |
| GraphQL request duration | ➕ NEW — instrument the `netbox_graphql` tool |
| GraphQL error / retry rate | ➕ NEW — instrument the tool |

Existing instrumentation to build on (do not duplicate):
- `src/middleware/metrics.py` — `QueryMetricsMiddleware`,
  `PerformanceMonitoringMiddleware`
- `src/utils/config.py` — `QueryMetrics` model
- `src/middleware/filter_recovery.py` — `MetricsMiddleware`

Add the 4 new axes as evaluators in `evaluators.py` and/or by surfacing existing
middleware metrics into the run record — whichever is cleaner. The generated PRP
decides where each metric is measured (evaluator vs. middleware vs. tool-level).

# THE A/B MECHANISM

The comparison is **GraphQL-enabled agent vs. MCP-only agent on the same 6
questions, same models**. Add a toggle so `create_netbox_agent()` can build the
agent with or without the `netbox_graphql` tool + skill — e.g. an
`EVAL_ENABLE_GRAPHQL` env flag consumed by `run_matrix_v3.py`, run twice
(baseline already exists as MCP-only; run once more with GraphQL enabled). The
generated PRP decides the exact toggle shape (env flag vs. a variant dimension in
the matrix). Keep experiment prefixes distinct so LangSmith sorts them as
separate, comparable experiments.

Reuse the existing skip-completed / quota-abort logic in `run_matrix_v3.py`.

# THE ROUTING SKILL

Create `src/skills/netbox-graphql/` with `SKILL.md` (+ `examples.md`),
mirroring the frontmatter + progressive-disclosure format of the existing
`src/skills/netbox-mcp-filters/SKILL.md` (`name` / `description` / `version` /
`tags` / `priority`). Add a one-line pointer from `netbox-mcp-filters` to it.

Routing policy the skill teaches:

| Query shape | Preferred tool |
|---|---|
| One object, or a simple filtered list | Existing MCP tool |
| Partial / fuzzy name search | Existing MCP search |
| Nested relationships across models | `netbox_graphql` |
| Three or more sequential reads joined by IDs | `netbox_graphql` |
| Unknown GraphQL type/field | Focused schema lookup, then `netbox_graphql` |
| Mutation / allocation request | Refuse — outside the agent's read-only scope |

Also teach: the NetBox 4.4 (Strawberry, 4.3-era) filter syntax; the
`{ field: undefined }` avoidance already relevant to this stack; and that GraphQL
is a complementary path, not a default — simple single-domain reads stay on MCP.

# SUCCESS CRITERIA (measurable — not "the agent used GraphQL")

For at least 3 representative cross-domain queries in `netbox-benchmark-v3`, the
GraphQL-enabled run vs. the MCP-only baseline shows:
- no completeness regression;
- no entity-coverage regression;
- fewer outer tool calls;
- lower median wall time, **or** a documented reason GraphQL should NOT become
  the default for that shape;

and, simultaneously:
- simple single-domain queries continue to prefer the MCP tools (the skill's
  routing holds — verify from traces that GraphQL is not over-selected).

A negative or mixed result is a valid, publishable outcome (consistent with this
project's "negative result done right" pattern) — the deliverable is the
measured verdict, not GraphQL adoption.

# EXISTING CODEBASE CONTEXT (read before implementing — verified)

- `tests/eval/dataset_v3.py`, `tests/eval/run_matrix_v3.py`,
  `tests/eval/evaluators.py`, `tests/eval/dataset.py` (v2, for the schema pattern)
- `docs/traces/2026-07-05_netbox-benchmark-v3_matrix.md` (MCP-only baseline) +
  `docs/traces/raw_2026-07-05_netbox-benchmark-v3/`
- `src/middleware/metrics.py`, `src/middleware/filter_recovery.py`,
  `src/utils/config.py` (`QueryMetrics`)
- `src/agents/netbox_agent.py` (`create_netbox_agent` — where the GraphQL toggle
  goes; note HarnessProfile "Workaround B")
- `src/skills/netbox-mcp-filters/SKILL.md` (format to mirror; add the pointer)
- `src/tools/netbox_graphql.py` (delivered by PRP 1)
- `docs/development/2026-06-03_quickjs-code-interpreter-research.md` §15 step 5
  (this A/B-per-model-with/without-a-feature methodology is already anticipated
  there)

# LIKELY FILE CHANGES

Create:
- `src/skills/netbox-graphql/SKILL.md`
- `src/skills/netbox-graphql/examples.md`
- `docs/traces/<date>_netbox-benchmark-v3_graphql-ab.md` (the A/B write-up,
  produced by the run)

Modify:
- `tests/eval/evaluators.py` (add wall-time / token / GraphQL-duration /
  GraphQL-error-rate axes)
- `tests/eval/run_matrix_v3.py` (honour the GraphQL toggle; record new metrics)
- `src/agents/netbox_agent.py` (GraphQL-enable toggle)
- `src/skills/netbox-mcp-filters/SKILL.md` (pointer to the new skill)
- `AGENTS.md` / `README.md` (document the routing policy + result)

# OUT OF SCOPE

Creating a new dataset (v3 exists — reuse it) · any write/mutation routing ·
Code Mode/QuickJS · changing the PRP-1 tool's security model · removing MCP
tools · declaring GraphQL the default before the measured criteria are met.

# DOCUMENTATION

- LangSmith evaluation: https://docs.smith.langchain.com/evaluation
- NetBox GraphQL (4.4 / Strawberry, 4.3 filtering):
  https://docs.netbox.dev/en/stable/integrations/graphql-api/
- The PRP-1 feature file: `PRPs/initials/netbox-graphql-read-tool.md`
