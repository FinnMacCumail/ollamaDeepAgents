# netbox-benchmark-v4 [timing-probe] — 2026-09-15 18:30 UTC

- Dataset: **netbox-benchmark-v4** (6 examples)
- Variant: **timing-probe** (baseline = no GraphQL tool; graphql = GraphQL tool wired in)
- Evaluators: entity_coverage · completeness · tool_calls · **correctness** (reference-grounded)

## Leaderboard (ranked by correctness ↓)

| # | Model (experiment) | correctness | completeness | entity_cov | tool_calls | errors |
|---|---|---|---|---|---|---|
| 1 | `ollama-deepseek-v4-pro-cloud-timing-probe-399667af` | 0.833 | 0.717 | 0.856 | 11.333 | 0 |
| 2 | `ollama-deepseek-v4-flash-cloud-timing-probe-fb309ac8` | 0.833 | 0.717 | 0.847 | 12.0 | 0 |

## Per-question detail

### `ollama-deepseek-v4-pro-cloud-timing-probe-399667af`

| question | correctness | completeness | entity_cov | tool_calls | err |
|---|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin s | 1.0 | 1.0 | 0.9474 | 28.0 |  |
| For device dmi01-nashua-rtr01, show location details, a | 1.0 | 0.5 | 0.5556 | 5.0 |  |
| For NC State University racks at Butler Communications  | 1.0 | 1.0 | 1.0 | 8.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking | 1.0 | 1.0 | 1.0 | 5.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack  | 0.5 | 0.0 | 0.8 | 5.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM | 0.5 | 0.8 | 0.8333 | 17.0 |  |

### `ollama-deepseek-v4-flash-cloud-timing-probe-fb309ac8`

| question | correctness | completeness | entity_cov | tool_calls | err |
|---|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin s | 1.0 | 1.0 | 0.8947 | 22.0 |  |
| For device dmi01-nashua-rtr01, show location details, a | 1.0 | 0.5 | 0.5556 | 13.0 |  |
| For NC State University racks at Butler Communications  | 1.0 | 1.0 | 1.0 | 15.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking | 1.0 | 1.0 | 1.0 | 6.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack  | 0.5 | 0.3 | 0.8 | 5.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM | 0.5 | 0.5 | 0.8333 | 11.0 |  |
