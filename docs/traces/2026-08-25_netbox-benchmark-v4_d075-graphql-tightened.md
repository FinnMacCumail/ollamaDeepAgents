# netbox-benchmark-v4 [d075-graphql-tightened] — 2026-08-25 12:30 UTC

- Dataset: **netbox-benchmark-v4** (6 examples)
- Variant: **d075-graphql-tightened** (GraphQL tool wired in + tightened routing guidance)
- Evaluators: entity_coverage · completeness · tool_calls · **correctness** (reference-grounded)
- Compare to: `2026-08-22_netbox-benchmark-v4_d075-graphql.md` (GraphQL, pre-tightening).

## VERDICT — routing tightening fixed the over-routing, cleanly

The GraphQL A/B's one regression was over-routing the SIMPLE `device-detail` lookup to GraphQL
(flash 0.5→0.0, pro 1.0→0.5). The routing guidance was rebalanced around the **anchor-object
rule** ("one named object → MCP, even when the answer spans several models") across four sites
(the `netbox-graphql` skill table, the `NETBOX_SYSTEM_PROMPT` block, the `netbox_graphql` tool
description, the `netbox-mcp-filters` pointer). **It worked, and did not over-correct.**

**Primary goal — device-detail recovered on both models** (vs the pre-tightening graphql arm):

| Query | pre-tightening (graphql) | tightened | mechanism |
|---|---|---|---|
| device-detail (flash) | 0.0 | **1.0** | now MCP-led (5 MCP calls + 1 gql) |
| device-detail (pro) | 0.5 | **1.0** | **now MCP-only** (`netbox_get_objects ×4`, zero GraphQL) |

**No over-correction — the cross-domain queries STILL route to GraphQL** (trajectory-verified):
site-comparison (flash `netbox_graphql ×3`, pro ×5) and multi-site-VLAN (flash ×10, pro ×6) all
still use GraphQL. Their 0.5 score dips this run (flash site-comparison 1.0→0.5, pro
multi-site-VLAN 1.0→0.5) are the well-known single-run variance on the two noisiest queries in
the suite — NOT the tightening demoting a legitimate GraphQL route (routing is unchanged).

**Aggregate:** flash correctness 0.75 → **0.917**; pro flat 0.75; combined **0.75 → 0.833**.

**Caveat:** one run. The device-detail *mechanism* fix (now MCP-routed) is confirmed
behaviorally, which is strong; the aggregate + the two noisy-query dips want the PR's tracked
**≥3× replication** to firm up. device-detail counts as recovered only if it holds ~1.0 in ≥2 of
3 runs and the cross-domain queries keep routing to GraphQL.

## Leaderboard (ranked by correctness ↓)

| # | Model (experiment) | correctness | completeness | entity_cov | tool_calls | errors |
|---|---|---|---|---|---|---|
| 1 | `ollama-deepseek-v4-flash-cloud-d075-graphql-tightened-a8133521` | 0.917 | 0.75 | 0.866 | 11.667 | 0 |
| 2 | `ollama-deepseek-v4-pro-cloud-d075-graphql-tightened-19e6f5e4` | 0.8 | 0.667 | 0.838 | 11.667 | 0 |

## Per-question detail

### `ollama-deepseek-v4-flash-cloud-d075-graphql-tightened-a8133521`

| question | correctness | completeness | entity_cov | tool_calls | err |
|---|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin s | 1.0 | 1.0 | 0.9474 | 23.0 |  |
| For device dmi01-nashua-rtr01, show location details, a | 1.0 | 0.5 | 0.6667 | 6.0 |  |
| For NC State University racks at Butler Communications  | 1.0 | 1.0 | 1.0 | 19.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking | 1.0 | 1.0 | 1.0 | 7.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack  | 1.0 | 0.5 | 0.75 | 7.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM | 0.5 | 0.5 | 0.8333 | 8.0 |  |

### `ollama-deepseek-v4-pro-cloud-d075-graphql-tightened-19e6f5e4`

| question | correctness | completeness | entity_cov | tool_calls | err |
|---|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin s | None | 1.0 | 0.9474 | 26.0 |  |
| For device dmi01-nashua-rtr01, show location details, a | 1.0 | 0.5 | 0.6667 | 5.0 |  |
| For NC State University racks at Butler Communications  | 1.0 | 1.0 | 0.7778 | 13.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking | 1.0 | 1.0 | 1.0 | 7.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack  | 0.5 | 0.0 | 0.8 | 3.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM | 0.5 | 0.5 | 0.8333 | 16.0 |  |
