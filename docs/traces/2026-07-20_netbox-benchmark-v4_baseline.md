# netbox-benchmark-v4 [baseline] — 2026-07-20 15:59 UTC

- Dataset: **netbox-benchmark-v4** (6 examples)
- Variant: **baseline** (baseline = no GraphQL tool; graphql = GraphQL tool wired in)
- Evaluators: entity_coverage · completeness · tool_calls · **correctness** (reference-grounded)

## Leaderboard (ranked by correctness ↓)

| # | Model (experiment) | correctness | completeness | entity_cov | tool_calls | errors |
|---|---|---|---|---|---|---|
| 1 | `ollama-deepseek-v4-flash-cloud-baseline-79e840d5` | 0.75 | 0.733 | 0.911 | 15.667 | 0 |
| 2 | `ollama-deepseek-v4-pro-cloud-baseline-2012c3a7` | 0.65 | 0.483 | 0.838 | 10.5 | 0 |

## Per-question detail

### `ollama-deepseek-v4-flash-cloud-baseline-79e840d5`

| question | correctness | completeness | entity_cov | tool_calls | err |
|---|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin s | 0.5 | 1.0 | 0.9474 | 10.0 |  |
| For device dmi01-nashua-rtr01, show location details, a | 1.0 | 1.0 | 1.0 | 6.0 |  |
| For NC State University racks at Butler Communications  | 1.0 | 0.5 | 1.0 | 12.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking | 1.0 | 1.0 | 1.0 | 46.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack  | 0.5 | 0.4 | 0.85 | 9.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM | 0.5 | 0.5 | 0.6667 | 11.0 |  |

### `ollama-deepseek-v4-pro-cloud-baseline-2012c3a7`

| question | correctness | completeness | entity_cov | tool_calls | err |
|---|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin s | 0.0 | 0.5 | 0.9474 | 12.0 |  |
| For device dmi01-nashua-rtr01, show location details, a | 1.0 | 0.5 | 0.6667 | 6.0 |  |
| For NC State University racks at Butler Communications  | 1.0 | 0.5 | 0.7778 | 13.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking | 1.0 | 0.5 | 1.0 | 5.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack  | 0.4 | 0.0 | 0.8 | 11.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM | 0.5 | 0.9 | 0.8333 | 16.0 |  |
