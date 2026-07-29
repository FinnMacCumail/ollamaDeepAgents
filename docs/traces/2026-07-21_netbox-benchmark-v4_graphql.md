# netbox-benchmark-v4 [graphql] — 2026-07-21 09:33 UTC

- Dataset: **netbox-benchmark-v4** (6 examples)
- Variant: **graphql** (baseline = no GraphQL tool; graphql = GraphQL tool wired in)
- Evaluators: entity_coverage · completeness · tool_calls · **correctness** (reference-grounded)

> **Baseline to compare against:** `2026-07-20_netbox-benchmark-v4_baseline.md`
> (same dataset, same references, same correctness judge; no GraphQL tool).

## VERDICT — PRP 2 A/B (GraphQL routing vs MCP-only)

**GraphQL routing is a measured correctness win on the cross-domain / aggregation
queries — the exact questions that hallucinated on every MCP-only run — at a
~2× tool-call cost, with an over-routing side-effect on one simple query.**

Head-to-head (correctness / tool_calls; baseline → graphql):

| Model | correctness | tool_calls |
|---|---|---|
| deepseek-v4-pro | 0.65 → **0.883** (+0.23) | 10.5 → 19.5 (+9) |
| deepseek-v4-flash | 0.75 → 0.75 (flat) | 15.7 → 27.0 (+11) |

The signal is per-question, not just aggregate:

- **site-comparison (IP allocation): 0.5 → 1.0 on BOTH models.** This is the trap
  that hallucinated a *different* fabricated utilization % on every MCP run this
  session (7.7 / 17.6 / 100 / 23.2). GraphQL's server-side join + prefix-membership
  reasoning avoids the "180 global IPs misattributed per-site" error. This
  reproduces the interactive-trace hypothesis (019f7cb6) inside the harness.
- **multi-site-vlan: pro 0.0 → 1.0.**
- **Cost:** ~2× tool calls on both models (GraphQL trades round-trips for a
  correct join). Documented, not a regression to fix blindly.
- **Over-routing side-effect:** flash **device-detail 1.0 → 0.5** — it applied
  GraphQL to a simple single-object lookup MCP handled fine and got a field
  wrong. This cancelled flash's site-comparison gain, leaving its aggregate flat.
  Matches the Gate-2 finding that routing is *soft* (the model sometimes
  over-selects GraphQL). The fix is tighter routing (keep simple lookups on MCP),
  not removing the tool.

Success criteria (from the PRP):

| Criterion | Result |
|---|---|
| GraphQL improves cross-domain correctness | ✅ site-comparison 0.5→1.0 both models; pro +0.23 overall |
| No correctness regression | ⚠️ improved on cross-domain; flash device-detail regressed (over-routing) |
| Fewer outer tool calls | ❌ ~2× more — the documented trade for correctness on hard queries |
| Simple queries stay on MCP | ⚠️ partial — flash over-applied GraphQL to device-detail |
| Generalizes beyond the benchmark | ✅ Gate 2: OOD circuits domain answered via pure introspection + GraphQL |

**Caveats.** One run per arm → the pro *aggregate* jump (0.65→0.883) is partly
variance; replicate ≥3× before quoting it. The **site-comparison 0.5→1.0 signal
is robust** (same mechanism, both models, matches the interactive trace). The
costs (tool calls, simple-query over-routing) are addressable by tightening the
routing skill, not by dropping GraphQL.

**Recommendation:** keep GraphQL as a complementary read path for cross-domain /
aggregation queries; tighten routing so simple single-object lookups stay on MCP;
do NOT make GraphQL the default. Re-run ≥3× per arm for a publishable aggregate.

---

## Raw results

## Leaderboard (ranked by correctness ↓)

| # | Model (experiment) | correctness | completeness | entity_cov | tool_calls | errors |
|---|---|---|---|---|---|---|
| 1 | `ollama-deepseek-v4-pro-cloud-graphql-1dac8ab1` | 0.883 | 0.667 | 0.875 | 19.5 | 0 |
| 2 | `ollama-deepseek-v4-flash-cloud-graphql-eca640f5` | 0.75 | 0.55 | 0.912 | 27.0 | 0 |

## Per-question detail

### `ollama-deepseek-v4-pro-cloud-graphql-1dac8ab1`

| question | correctness | completeness | entity_cov | tool_calls | err |
|---|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin s | 1.0 | 1.0 | 0.9474 | 28.0 |  |
| For device dmi01-nashua-rtr01, show location details, a | 1.0 | 0.5 | 0.6667 | 8.0 |  |
| For NC State University racks at Butler Communications  | 1.0 | 1.0 | 1.0 | 11.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking | 1.0 | 1.0 | 1.0 | 38.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack  | 0.3 | 0.0 | 0.8 | 10.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM | 1.0 | 0.5 | 0.8333 | 22.0 |  |

### `ollama-deepseek-v4-flash-cloud-graphql-eca640f5`

| question | correctness | completeness | entity_cov | tool_calls | err |
|---|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin s | 0.5 | 0.0 | 0.9474 | 34.0 |  |
| For device dmi01-nashua-rtr01, show location details, a | 0.5 | 0.5 | 0.8889 | 9.0 |  |
| For NC State University racks at Butler Communications  | 1.0 | 1.0 | 1.0 | 12.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking | 1.0 | 1.0 | 1.0 | 69.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack  | 0.5 | 0.0 | 0.8 | 9.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM | 1.0 | 0.8 | 0.8333 | 29.0 |  |
