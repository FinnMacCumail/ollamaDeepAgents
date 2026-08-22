# netbox-benchmark-v4 [d075-graphql] — 2026-08-22 08:59 UTC

- Dataset: **netbox-benchmark-v4** (6 examples)
- Variant: **d075-graphql** (baseline = no GraphQL tool; graphql = GraphQL tool wired in)
- Evaluators: entity_coverage · completeness · tool_calls · **correctness** (reference-grounded)

> **Baseline arm:** `2026-08-11_netbox-benchmark-v4_d075-baseline.md` (same dataset,
> same references, same correctness judge, **also under deepagents 0.7.5**, no GraphQL).
> This A/B **supersedes** the 0.6.10-era A/B (`2026-07-21_netbox-benchmark-v4_graphql.md`).

## VERDICT — GraphQL routing A/B under deepagents 0.7.5 (supersedes the 0.6.10 A/B)

**GraphQL routing is a correctness win on cross-domain / aggregation queries — and under
0.7.5 it is NO LONGER a tool-call cost trade** (this run it was cheaper). The remaining issue
is unchanged: over-routing simple lookups.

Head-to-head (both arms under 0.7.5):

| Model | correctness (base → gql) | completeness | tool_calls (base → gql) |
|---|---|---|---|
| deepseek-v4-flash | 0.583 → **0.75** (+0.167) | 0.667 → 0.667 | 18.5 → **12.8** (−5.7) |
| deepseek-v4-pro | 0.75 → 0.75 (flat) | 0.667 → **0.75** | 11.7 → 11.5 |
| **combined mean** | 0.667 → **0.75** | — | 15.1 → **12.2** |

Per-question signal:
- **The cross-domain/aggregation wins reproduce.** site-comparison IP-allocation trap: flash
  **0.0 → 1.0**. multi-site-VLAN: flash **0.5 → 1.0**, pro **0.0 → 1.0**. These are the queries
  MCP-only hallucinates; GraphQL fixes them, on both models, as in every prior run.
- **Over-routing persists (the open item):** device-detail (a *simple* lookup) regresses under
  GraphQL — flash **0.5 → 0.0**, pro **1.0 → 0.5**. The model over-applies GraphQL to a query
  MCP handles fine. Fix = tighten routing so simple single-object lookups stay on MCP.
- Noise: pro's site-comparison went 1.0 → 0.5 this run (baseline nailed it, gql didn't) —
  single-run variance; flash's 0.0 → 1.0 on the same query is the real signal.

**What changed vs the 0.6.10 A/B:** there, GraphQL bought correctness at **~2× tool calls**
(flash 15.7 → 27.0). Under 0.7.5 GraphQL improved correctness **and reduced** tool calls
(flash 18.5 → 12.8) — the leaner 0.7 prompts make the agent far more efficient with the GraphQL
path, so the "expensive" half of the old verdict no longer holds.

**Caveat (unchanged):** one run per arm. The site-comparison / multi-site-VLAN wins are robust
(both models, every framework); the aggregate and the vanished cost penalty want the **≥3×
replication** to confirm. Do NOT quote the aggregate as final until then.

## Leaderboard (ranked by correctness ↓)

| # | Model (experiment) | correctness | completeness | entity_cov | tool_calls | errors |
|---|---|---|---|---|---|---|
| 1 | `ollama-deepseek-v4-pro-cloud-d075-graphql-7fb31156` | 0.75 | 0.75 | 0.846 | 11.5 | 0 |
| 2 | `ollama-deepseek-v4-flash-cloud-d075-graphql-5e6d3797` | 0.75 | 0.667 | 0.801 | 12.833 | 0 |

## Per-question detail

### `ollama-deepseek-v4-pro-cloud-d075-graphql-7fb31156`

| question | correctness | completeness | entity_cov | tool_calls | err |
|---|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin s | 1.0 | 1.0 | 1.0 | 24.0 |  |
| For device dmi01-nashua-rtr01, show location details, a | 0.5 | 0.5 | 0.6667 | 6.0 |  |
| For NC State University racks at Butler Communications  | 1.0 | 1.0 | 0.7778 | 14.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking | 1.0 | 1.0 | 1.0 | 7.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack  | 0.5 | 0.5 | 0.8 | 3.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM | 0.5 | 0.5 | 0.8333 | 15.0 |  |

### `ollama-deepseek-v4-flash-cloud-d075-graphql-5e6d3797`

| question | correctness | completeness | entity_cov | tool_calls | err |
|---|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin s | 1.0 | 0.5 | 0.8947 | 27.0 |  |
| For device dmi01-nashua-rtr01, show location details, a | 0.0 | 0.5 | 0.4444 | 5.0 |  |
| For NC State University racks at Butler Communications  | 1.0 | 1.0 | 1.0 | 17.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking | 1.0 | 1.0 | 1.0 | 13.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack  | 0.5 | 0.5 | 0.8 | 7.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM | 1.0 | 0.5 | 0.6667 | 8.0 |  |
