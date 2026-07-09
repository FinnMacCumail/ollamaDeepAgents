# netbox-benchmark-v3 model-matrix run — 2026-07-05 13:15 UTC

- Dataset: **netbox-benchmark-v3** (6 cross-domain examples)
- Evaluators: entity_coverage (code) · completeness (LLM-judge, gpt-oss:20b) · tool_calls (trajectory)
- Models: 9 (gemini-3-flash excluded)

## Leaderboard

Sorted by completeness ↓, then entity_coverage ↓, then tool_calls ↑.

| # | Model (experiment) | entity_cov | completeness | tool_calls | runs | errors |
|---|---|---|---|---|---|---|
| 1 | `ollama-deepseek-v4-flash-cloud-07b5f223` | 0.929 | 0.8 | 21.0 | 6 | 0 |
| 2 | `ollama-nemotron-3-ultra-cloud-6f63db80` | 0.871 | 0.733 | 20.833 | 6 | 0 |
| 3 | `ollama-glm-5-cloud-ba2dfa61` | 0.93 | 0.725 | 9.167 | 6 | 0 |
| 4 | `ollama-deepseek-v4-pro-cloud-0456554e` | 0.902 | 0.717 | 10.5 | 6 | 0 |
| 5 | `ollama-minimax-m3-cloud-37223120` | 0.828 | 0.717 | 21.5 | 6 | 0 |
| 6 | `ollama-kimi-k2.6-cloud-7c4a82a0` | 0.876 | 0.667 | 13.5 | 6 | 0 |
| 7 | `ollama-qwen3.5-397b-cloud-80ae2463` | 0.932 | 0.583 | 15.667 | 6 | 0 |
| 8 | `ollama-nemotron-3-super-cloud-88d5ed35` | 0.419 | 0.25 | 13.2 | 6 | 1 |
| 9 | `ollama-gpt-oss-120b-cloud-f6482d71` | 0.302 | 0.25 | 5.5 | 6 | 2 |

## Per-question detail

### `ollama-deepseek-v4-flash-cloud-07b5f223`

| question | entity_cov | completeness | tool_calls | err |
|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin sites, | 1.0 | 0.9 | 75.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM-Akro | 0.8333 | 0.9 | 11.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking site | 1.0 | 1.0 | 16.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack alloc | 0.85 | 0.5 | 7.0 |  |
| For device dmi01-nashua-rtr01, show location details, assign | 0.8889 | 0.5 | 7.0 |  |
| For NC State University racks at Butler Communications site, | 1.0 | 1.0 | 10.0 |  |

### `ollama-nemotron-3-ultra-cloud-6f63db80`

| question | entity_cov | completeness | tool_calls | err |
|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin sites, | 0.8421 | 0.0 | 12.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM-Akro | 0.8333 | 0.9 | 14.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking site | 0.75 | 1.0 | 21.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack alloc | 0.8 | 0.5 | 47.0 |  |
| For device dmi01-nashua-rtr01, show location details, assign | 1.0 | 1.0 | 12.0 |  |
| For NC State University racks at Butler Communications site, | 1.0 | 1.0 | 19.0 |  |

### `ollama-glm-5-cloud-ba2dfa61`

| question | entity_cov | completeness | tool_calls | err |
|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin sites, | 0.8947 | 0.0 | 8.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM-Akro | 0.8333 | 0.85 | 15.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking site | 1.0 | 1.0 | 9.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack alloc | 0.85 | 0.5 | 6.0 |  |
| For device dmi01-nashua-rtr01, show location details, assign | 1.0 | 1.0 | 9.0 |  |
| For NC State University racks at Butler Communications site, | 1.0 | 1.0 | 8.0 |  |

### `ollama-deepseek-v4-pro-cloud-0456554e`

| question | entity_cov | completeness | tool_calls | err |
|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin sites, | 1.0 | 1.0 | 14.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM-Akro | 0.8333 | 0.8 | 8.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking site | 1.0 | 1.0 | 9.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack alloc | 0.8 | 0.0 | 15.0 |  |
| For device dmi01-nashua-rtr01, show location details, assign | 0.8889 | 0.5 | 6.0 |  |
| For NC State University racks at Butler Communications site, | 0.8889 | 1.0 | 11.0 |  |

### `ollama-minimax-m3-cloud-37223120`

| question | entity_cov | completeness | tool_calls | err |
|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin sites, | 0.9474 | 1.0 | 17.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM-Akro | 0.8333 | 0.8 | 21.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking site | 0.5 | 0.5 | 19.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack alloc | 0.8 | 0.5 | 38.0 |  |
| For device dmi01-nashua-rtr01, show location details, assign | 0.8889 | 0.5 | 12.0 |  |
| For NC State University racks at Butler Communications site, | 1.0 | 1.0 | 22.0 |  |

### `ollama-kimi-k2.6-cloud-7c4a82a0`

| question | entity_cov | completeness | tool_calls | err |
|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin sites, | 0.8947 | 0.0 | 8.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM-Akro | 0.8333 | 0.5 | 11.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking site | 1.0 | 1.0 | 33.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack alloc | 0.75 | 0.5 | 9.0 |  |
| For device dmi01-nashua-rtr01, show location details, assign | 0.8889 | 1.0 | 13.0 |  |
| For NC State University racks at Butler Communications site, | 0.8889 | 1.0 | 7.0 |  |

### `ollama-qwen3.5-397b-cloud-80ae2463`

| question | entity_cov | completeness | tool_calls | err |
|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin sites, | 0.8421 | 0.0 | 6.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM-Akro | 1.0 | 1.0 | 15.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking site | 1.0 | 0.5 | 18.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack alloc | 0.75 | 0.5 | 44.0 |  |
| For device dmi01-nashua-rtr01, show location details, assign | 1.0 | 1.0 | 4.0 |  |
| For NC State University racks at Butler Communications site, | 1.0 | 0.5 | 7.0 |  |

### `ollama-nemotron-3-super-cloud-88d5ed35`

| question | entity_cov | completeness | tool_calls | err |
|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin sites, | 0.7368 | 0.5 | 11.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM-Akro | 0.6667 | 0.5 | 28.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking site | 0.0 | 0.0 | 9.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack alloc | 0.0 | 0.0 | None | ✗ |
| For device dmi01-nashua-rtr01, show location details, assign | 0.3333 | 0.0 | 5.0 |  |
| For NC State University racks at Butler Communications site, | 0.7778 | 0.5 | 13.0 |  |

### `ollama-gpt-oss-120b-cloud-f6482d71`

| question | entity_cov | completeness | tool_calls | err |
|---|---|---|---|---|
| Show where VLAN 100 is deployed across Dunder-Mifflin sites, | 0.8421 | 0.5 | 5.0 |  |
| Compare infrastructure utilization across DM-Nashua, DM-Akro | 0.1667 | 0.0 | 2.0 |  |
| Show where VLAN 100 is deployed across Jimbob's Banking site | 0.25 | 1.0 | 10.0 |  |
| Show all Dunder-Mifflin sites with device counts, rack alloc | 0.0 | 0.0 | None | ✗ |
| For device dmi01-nashua-rtr01, show location details, assign | 0.5556 | 0.0 | 5.0 |  |
| For NC State University racks at Butler Communications site, | 0.0 | 0.0 | None | ✗ |
