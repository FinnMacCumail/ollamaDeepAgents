# netbox-benchmark-v4 [d075-tightened-r2] — 2026-08-25 15:25 UTC

- Dataset: **netbox-benchmark-v4** (6 examples)
- Variant: **d075-tightened-r2** (baseline = no GraphQL tool; graphql = GraphQL tool wired in)
- Evaluators: entity_coverage · completeness · tool_calls · **correctness** (reference-grounded)

## Leaderboard (ranked by correctness ↓)

| # | Model (experiment) | correctness | completeness | entity_cov | tool_calls | errors |
|---|---|---|---|---|---|---|
| 1 | `ollama-deepseek-v4-flash-cloud-d075-tightened-r2-357afca8` | 0.833 | 0.667 | 0.684 | 9.5 | 0 |
| 2 | `ollama-deepseek-v4-pro-cloud-d075-tightened-r2-2703186a` | 0.817 | 0.75 | 0.855 | 13.167 | 0 |

## Per-question detail

### `ollama-deepseek-v4-flash-cloud-d075-tightened-r2-357afca8`

| question | correctness | completeness | entity_cov | tool_calls | err |
|---|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin s | 1.0 | 1.0 | 0.9474 | 19.0 |  |
| For device dmi01-nashua-rtr01, show location details, a | 1.0 | 0.0 | 0.0 | 4.0 |  |
| For NC State University racks at Butler Communications  | 1.0 | 1.0 | 0.8889 | 12.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking | 1.0 | 1.0 | 0.75 | 4.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack  | 0.5 | 0.5 | 0.85 | 10.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM | 0.5 | 0.5 | 0.6667 | 8.0 |  |

### `ollama-deepseek-v4-pro-cloud-d075-tightened-r2-2703186a`

| question | correctness | completeness | entity_cov | tool_calls | err |
|---|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin s | 1.0 | 1.0 | 1.0 | 31.0 |  |
| For device dmi01-nashua-rtr01, show location details, a | 1.0 | 0.5 | 0.6667 | 6.0 |  |
| For NC State University racks at Butler Communications  | 1.0 | 1.0 | 0.7778 | 10.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking | 1.0 | 1.0 | 1.0 | 6.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack  | 0.4 | 0.5 | 0.85 | 6.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM | 0.5 | 0.5 | 0.8333 | 20.0 |  |
