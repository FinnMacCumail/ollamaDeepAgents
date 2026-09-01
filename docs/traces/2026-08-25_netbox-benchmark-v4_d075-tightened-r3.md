# netbox-benchmark-v4 [d075-tightened-r3] — 2026-08-25 15:38 UTC

- Dataset: **netbox-benchmark-v4** (6 examples)
- Variant: **d075-tightened-r3** (baseline = no GraphQL tool; graphql = GraphQL tool wired in)
- Evaluators: entity_coverage · completeness · tool_calls · **correctness** (reference-grounded)

## Leaderboard (ranked by correctness ↓)

| # | Model (experiment) | correctness | completeness | entity_cov | tool_calls | errors |
|---|---|---|---|---|---|---|
| 1 | `ollama-deepseek-v4-flash-cloud-d075-tightened-r3-d0fcfbab` | 0.833 | 0.7 | 0.912 | 13.167 | 0 |
| 2 | `ollama-deepseek-v4-pro-cloud-d075-tightened-r3-dfbdee64` | 0.75 | 0.75 | 0.883 | 14.167 | 0 |

## Per-question detail

### `ollama-deepseek-v4-flash-cloud-d075-tightened-r3-d0fcfbab`

| question | correctness | completeness | entity_cov | tool_calls | err |
|---|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin s | 0.5 | 0.9 | 0.9474 | 19.0 |  |
| For device dmi01-nashua-rtr01, show location details, a | 1.0 | 0.5 | 0.8889 | 6.0 |  |
| For NC State University racks at Butler Communications  | 1.0 | 1.0 | 1.0 | 21.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking | 1.0 | 1.0 | 1.0 | 8.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack  | 0.5 | 0.3 | 0.8 | 9.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM | 1.0 | 0.5 | 0.8333 | 16.0 |  |

### `ollama-deepseek-v4-pro-cloud-d075-tightened-r3-dfbdee64`

| question | correctness | completeness | entity_cov | tool_calls | err |
|---|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin s | 1.0 | 1.0 | 0.9474 | 29.0 |  |
| For device dmi01-nashua-rtr01, show location details, a | 0.5 | 0.5 | 0.6667 | 9.0 |  |
| For NC State University racks at Butler Communications  | 1.0 | 1.0 | 1.0 | 11.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking | 1.0 | 1.0 | 1.0 | 10.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack  | 0.5 | 0.5 | 0.85 | 4.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM | 0.5 | 0.5 | 0.8333 | 22.0 |  |
