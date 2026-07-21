# PRP: GraphQL Routing Skill + Eval A/B

**Feature file:** `PRPs/initials/netbox-graphql-routing-and-evaluation.md`
**Generated:** 2026-07-20 (generate-prp workflow, on branch `feat/graphql-read-tool`)
**Scope:** PRP **2 of 2**. Teaches the agent *when* to use `netbox_graphql`
(PRP 1) and measures whether it helps — no new tool.
**Confidence for one-pass implementation: 7/10** (the skill + prompt change are
deterministic; the *verdict* is empirical and subject to run variance).

---

## Reconciliation with current reality (READ FIRST)

The initial was written against v3 with an `EVAL_ENABLE_GRAPHQL` env toggle.
Since then the ground shifted — the generated PRP uses the current reality:

| Initial said | Now |
|---|---|
| A/B on `netbox-benchmark-v3` | **`netbox-benchmark-v4`** (corrected refs + `correctness_judge`) |
| Baseline = 2026-07-05 v3 run | **Committed v4 baseline** (`docs/traces/2026-07-20_netbox-benchmark-v4_baseline.md`, experiments `ollama-*-baseline-*`) |
| Build an `EVAL_ENABLE_GRAPHQL` toggle in `run_matrix_v3` | **Already built:** `run_matrix_v4.py` + `EVAL_VARIANT`. The A/B is driven by **git branch** — `master` = no GraphQL tool (baseline); this branch = GraphQL wired in (graphql). No new toggle needed. |
| 3 of 7 metrics exist | Now **4** exist (correctness added). wall-time/tokens/gql-duration/gql-error remain optional. |

**So the only genuinely NEW code in PRP 2 is: (1) the routing skill, (2) a
system-prompt change so the model is *allowed* to route to GraphQL, (3) optional
metric axes.** Then run the graphql arm and compare to the committed baseline.

## Goal

Make the agent choose `netbox_graphql` for nested/cross-model reads (and stay on
MCP for simple ones), then measure GraphQL-arm vs baseline on v4. A negative or
mixed result is a valid, publishable outcome.

## Why

We proved (trace `019f7cb6`, and the QuickJS spike before it) that the agent
**will not use `netbox_graphql` unless steered** — the system prompt at
`netbox_agent.py:140` says *"ALWAYS check the netbox-mcp-filters skill,"* which
routes everything to the MCP path. And when forced to use GraphQL, the model paid
a **7-call schema-discovery tax** and thrashed on `IPAddressFilter`. The skill
must both *permit* routing and *pre-load the schema gotchas* to make it efficient.

## What (success criteria — measurable)

For ≥3 cross-domain queries in v4, graphql-arm vs baseline:
- [ ] **no correctness regression** (the axis that matters most now);
- [ ] no completeness/entity-coverage regression;
- [ ] fewer outer tool calls **or** a documented reason not to default to GraphQL;
- [ ] simple single-domain queries still prefer MCP (verify from traces GraphQL is not over-selected).
- [ ] The routing skill loads and the model actually invokes `netbox_graphql` on the nested queries (baseline of the QuickJS failure mode).
- [ ] **Generalization (not overfitting):** the skill drives *correct* GraphQL on
      **≥3 out-of-benchmark domains** — e.g. power (`PowerFeedType`), circuits
      (`CircuitType`/`ProviderType`), wireless (`WirelessLANType`) — with the
      model introspecting the right `<Model>Type` via `netbox_graphql_schema`
      first. If it only works on the 6 benchmark shapes, the skill is overfit and
      the PRP is NOT done.

**Testable hypothesis to report on:** in trace `019f7cb6`, GraphQL-forced flash
got `site-comparison` IP-allocation **right (0%)** by checking prefix membership,
while the MCP path hallucinated 17.6%. So GraphQL routing *may improve correctness
on the IP-allocation trap* at the cost of more tool calls. The A/B tests this.

---

## All Needed Context

### DESIGN PRINCIPLE #1 — generalize to ANY NetBox GraphQL query (do NOT overfit the benchmark)

The skill MUST work for arbitrary NetBox queries (power feeds, circuits, wireless,
tenancy, VMs, plugin objects — anything), not just the 6 benchmark shapes. NetBox
has ~100+ object types plus plugins; enumerating them is impossible and violates
the <500-line progressive-disclosure limit. Generalization therefore comes from
teaching **grammar + runtime introspection**, never a schema dump:

- **Teach the universal grammar** (identical for every type): root fields are
  `<model>_list` (`powerfeed_list`, `circuit_list`, `wirelesslan_list`, ...);
  types are `<Model>Type`; IDs bare; strings as `{exact:}`/`{in_list:}`/
  `{i_contains:}`; nested relationship filters; field selection. These let the
  model write valid syntax for a type it has never seen.
- **Teach runtime discovery as THE generalization engine:** for ANY unfamiliar
  type/field the model MUST call `netbox_graphql_schema(<Model>Type)` first (it
  reads the LIVE schema, incl. plugins) rather than guessing. This is what makes
  the skill cover types absent from the demo data.
- **Teach gotchas as PATTERNS, not instances:** e.g. "reverse-relation filters
  may not exist (`IPAddressFilter` has no `device`) — prefer the forward
  direction or a `parent`/`scope` filter" generalizes far beyond IPs.

HARD RULES for whoever executes this PRP:
- Do NOT hardcode benchmark object types, demo-data names, or the 6 benchmark
  queries as the schema. `examples.md` illustrates *patterns*; every example must
  carry an explicit "adapt to any type via `netbox_graphql_schema`" note.
- The benchmark A/B does NOT prove generalization (an overfit skill would also
  pass it) — generalization is validated separately by the out-of-distribution
  smoke queries in Gate 2 and the acceptance criteria.

### The load-bearing change: the system-prompt bias (`netbox_agent.py`)

- Line ~140: `"- ALWAYS check the netbox-mcp-filters skill for filter guidance"`.
  This (plus the `netbox-mcp-filters` skill's MCP-decomposition content) is why
  the model never spontaneously routes to GraphQL. PRP 2 must add a sibling line
  that *permits and directs* GraphQL for nested reads, e.g.:
  `"- For nested / cross-model reads or 3+-hop joins, prefer the netbox_graphql tool — see the netbox-graphql skill. Keep simple single-object lookups on the MCP tools."`
  Keep it minimal; do not remove the MCP guidance.
- The GraphQL tools are always present on this branch (PRP 1 wired them into the
  `tools` list). No conditional loading needed — `master` simply lacks the tool
  (that IS the baseline arm).

### Skill format to mirror (`src/skills/netbox-mcp-filters/SKILL.md`)

Frontmatter (required — loader needs `name`; see AGENTS.md §4):
```yaml
---
name: netbox-graphql
description: <when to load — nested/cross-model reads, 3+-hop joins; NetBox GraphQL grammar>
version: 1.0.0
tags: [netbox, graphql, routing, cross-domain]
priority: high
---
```
Progressive disclosure: `SKILL.md` (<500 lines core) + `examples.md` (loaded on
demand). Add a one-line pointer from `netbox-mcp-filters/SKILL.md` to it.

### Schema gotchas to BAKE INTO the skill (live-verified 2026-07-20)

These kill the 7-call discovery tax and the `IPAddressFilter` thrash:
- Endpoint is read-only; **refuse mutations** (the tool also rejects them).
- Root query fields are `<model>_list`: `device_list`, `site_list`, `vlan_list`,
  `ipaddress_list`, `prefix_list`, `cable_list`, `circuit_list`.
- Types are `<Model>Type` (e.g. `DeviceType`, `SiteType`) — call
  `netbox_graphql_schema` with that name to list fields.
- **ID filters are bare**: `{id: 6}` or `{id: [6, 7]}`. NOT `{id: {exact: 6}}`
  (that is 4.5 syntax and FAILS here).
- **String filters use lookup objects**: `{name: {exact: "..."}}`,
  `{name: {i_contains: "..."}}`, `{name: {in_list: ["a","b"]}}`.
- **Nested relationship filters WORK** (the whole point — MCP cannot):
  `device_list(filters: {site: {name: {in_list: ["DM-Nashua","DM-Akron"]}}})`.
- **`IPAddressFilter` does NOT nest through `device`** — `ip_address_list(filters:
  {device: {...}})` FAILS. To scope IPs, filter by `parent` (prefix) or go via
  interfaces. (This is the exact friction from trace `019f7cb6`.)
- Omit optional keys; never pass `{field: undefined}`.
- Prefer field selection to keep payloads small (results never re-enter context
  the way MCP JSON does).

### Routing policy (the skill's core table)

| Query shape | Tool |
|---|---|
| One object / simple filtered list | MCP `netbox_get_objects` |
| Partial / fuzzy name search | MCP `netbox_search_objects` |
| Nested relationships across models | `netbox_graphql` |
| 3+ sequential reads joined by IDs | `netbox_graphql` |
| Unknown GraphQL type/field | `netbox_graphql_schema` then `netbox_graphql` |
| Aggregations/counts/percentages (e.g. IP utilization) | `netbox_graphql` to fetch, **but compute the count client-side and verify prefix membership** (do not report global IP counts as per-site) |
| Mutation / allocation | Refuse — read-only scope |

### The A/B mechanism (already built — just run it)

- `run_matrix_v4.py` + `EVAL_VARIANT`. On this branch:
  `EVAL_VARIANT=graphql ./venv/bin/python -m tests.eval.run_matrix_v4`
  → experiments `ollama-*-graphql-*` under `netbox-benchmark-v4`, scored with
  `ALL_EVALUATORS` (incl. correctness).
- Baseline already exists: `ollama-*-baseline-*`. Compare graphql vs baseline.
- Production pair by default (`deepseek-v4-flash` + `pro`); `EVAL_MODELS` widens.
- **Variance caveat (hard-won this session):** single runs of 6 questions are
  noisy (correctness swung ±0.15–0.25; the flash-vs-pro ranking flipped across
  runs). Run **each arm ≥3×** (or state the caveat) before any verdict.

### Metrics extension (OPTIONAL — secondary)

correctness/completeness/entity/tool_calls already cover the core verdict. If
adding the 4 initial extras (wall-time, tokens, gql-duration, gql-error-rate):
surface wall-time/tokens from the existing `QueryMetricsMiddleware` /
`PerformanceMonitoringMiddleware` (`src/middleware/metrics.py`); instrument
gql-duration/error-rate inside `netbox_graphql.py`. Do NOT rebuild metrics infra.
Mark as a follow-up if it risks scope creep.

---

## Implementation Blueprint

### Task order

1. **Author `src/skills/netbox-graphql/SKILL.md`** — frontmatter + routing table
   + the schema gotchas above + read-only rule + "complementary, not default".
2. **`src/skills/netbox-graphql/examples.md`** — worked queries that teach
   *patterns*, each explicitly labelled "adapt to any `<Model>Type` via
   `netbox_graphql_schema`". Cover: device→site→region; multi-site list via
   `in_list`; a nested relationship filter; the IP-allocation pattern (fetch
   prefixes, count client-side, verify membership — do NOT report the 172.16
   global IPs as per-site); AND **at least one out-of-benchmark domain**
   (e.g. power feed → power panel, or circuit → provider → termination) to prove
   the pattern is domain-agnostic. Lead with the discovery step
   (`netbox_graphql_schema(<Type>)`) in every non-trivial example.
3. **`netbox_agent.py`** — add the one sibling system-prompt line permitting
   GraphQL routing for nested reads. Add the pointer in `netbox-mcp-filters/SKILL.md`.
4. **(optional) metric axes** in `evaluators.py` / surfaced from middleware.
5. **Run the graphql arm** (`EVAL_VARIANT=graphql`, ≥3× if measuring a verdict).
6. **Write the A/B doc** `docs/traces/2026-07-20_netbox-benchmark-v4_graphql-ab.md`
   comparing graphql vs baseline per question, and verifying from traces that
   (a) the model actually used GraphQL on nested queries and (b) did NOT over-use
   it on simple ones.
7. Update `AGENTS.md` / `README.md` with the routing policy + the measured verdict.

### Pseudocode — the routing decision (as taught in the skill, not code)

```
if query is a single object / simple filter / fuzzy search:  use MCP
elif query spans >=2 models or needs 3+ ID-joined reads:      use netbox_graphql
    if unsure of fields:  netbox_graphql_schema(TypeName) first
    remember: IDs bare, strings {exact:}/{in_list:}, IPs by parent-prefix
elif mutation/allocation:  refuse (read-only)
else:  use MCP
```

---

## Validation Loop

### Gate 1 — skill + prompt wiring
```bash
./venv/bin/ruff check src/agents/netbox_agent.py
# skill loads without loader warnings:
./venv/bin/python -c "import asyncio; from src.agents.netbox_agent import create_netbox_agent; \
asyncio.run(create_netbox_agent())" 2>&1 | grep -i 'skill loader' || echo "no skill-loader warnings"
```

### Gate 2 — the model routes correctly AND generalizes (interactive smoke)
```bash
./venv/bin/python -m src.main
#  nested (benchmark shape) -> "Compare infrastructure utilization across DM-Nashua, DM-Akron, DM-Scranton..."
#           EXPECT: model invokes netbox_graphql (not forced) — check the trace.
#  simple -> "Show device dmi01-nashua-rtr01"
#           EXPECT: model stays on netbox_get_objects.
#
#  OUT-OF-BENCHMARK generalization (domains NOT in netbox-benchmark-v4) —
#  the real test of the skill. EXPECT: model introspects the right <Model>Type
#  via netbox_graphql_schema, then writes a valid nested query:
#    - "Which power feeds supply devices in rack IDF128, and from which power panel?"
#    - "List circuits from each provider and the sites where they terminate"
#    - "Show wireless LANs and the interfaces attached to them"
#  A model that can only answer the 6 benchmark shapes = overfit skill (FAIL).
```

### Gate 3 — the A/B (the deliverable)
```bash
# on this branch (GraphQL wired in):
EVAL_VARIANT=graphql ./venv/bin/python -m tests.eval.run_matrix_v4
# compare ollama-*-graphql-* vs the committed ollama-*-baseline-* on netbox-benchmark-v4.
# Run >=3x per arm (or record the variance caveat) before stating a verdict.
```
Pass = success criteria above met, OR a documented, measured reason GraphQL
should not become the default. Report, don't assume.

---

## Out of scope

New dataset (v4 exists) · write/mutation routing · Code Mode/QuickJS · changing
PRP-1's security model · removing MCP tools · declaring GraphQL the default before
the criteria are met · a full metrics-infra rebuild.

## Confidence: 7/10

The skill + prompt change are deterministic and low-risk (mirrors an existing
skill). The −3 is inherent: whether the model reliably routes, and whether
GraphQL actually improves correctness/tool-calls, are empirical questions the A/B
answers — and single-run scores are noisy (documented). The interactive-trace
evidence (`019f7cb6`) suggests GraphQL *can* improve site-comparison correctness,
but that must be shown across ≥3 runs, not asserted.
