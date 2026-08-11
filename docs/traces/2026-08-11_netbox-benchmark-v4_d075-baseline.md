# netbox-benchmark-v4 [d075-baseline] — 2026-08-11 13:19 UTC

- Dataset: **netbox-benchmark-v4** (6 examples)
- Variant: **d075-baseline** (baseline = no GraphQL tool; graphql = GraphQL tool wired in)
- Evaluators: entity_coverage · completeness · tool_calls · **correctness** (reference-grounded)

## Leaderboard (ranked by correctness ↓)

| # | Model (experiment) | correctness | completeness | entity_cov | tool_calls | errors |
|---|---|---|---|---|---|---|
| 1 | `ollama-deepseek-v4-pro-cloud-d075-baseline-525ede9b` | 0.75 | 0.667 | 0.901 | 11.667 | 0 |
| 2 | `ollama-deepseek-v4-flash-cloud-d075-baseline-2c6340f4` | 0.583 | 0.667 | 0.848 | 18.5 | 0 |

## Per-question detail

### `ollama-deepseek-v4-pro-cloud-d075-baseline-525ede9b`

| question | correctness | completeness | entity_cov | tool_calls | err |
|---|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin s | 0.0 | 0.0 | 0.8947 | 9.0 |  |
| For device dmi01-nashua-rtr01, show location details, a | 1.0 | 1.0 | 0.8889 | 7.0 |  |
| For NC State University racks at Butler Communications  | 1.0 | 1.0 | 0.8889 | 19.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking | 1.0 | 1.0 | 1.0 | 13.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack  | 0.5 | 0.5 | 0.9 | 7.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM | 1.0 | 0.5 | 0.8333 | 15.0 |  |

### `ollama-deepseek-v4-flash-cloud-d075-baseline-2c6340f4`

| question | correctness | completeness | entity_cov | tool_calls | err |
|---|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin s | 0.5 | 0.5 | 0.9474 | 20.0 |  |
| For device dmi01-nashua-rtr01, show location details, a | 0.5 | 0.5 | 0.6667 | 9.0 |  |
| For NC State University racks at Butler Communications  | 1.0 | 1.0 | 0.8889 | 9.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking | 1.0 | 1.0 | 1.0 | 6.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack  | 0.5 | 0.5 | 0.75 | 52.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM | 0.0 | 0.5 | 0.8333 | 15.0 |  |
