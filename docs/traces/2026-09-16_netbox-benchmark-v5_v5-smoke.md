# netbox-benchmark-v5 [v5-smoke] — 2026-09-16 15:06 UTC

- Dataset: **netbox-benchmark-v5** (15 examples)
- Evaluators: entity_coverage · completeness · tool_calls · **correctness**
- Tool-call budgets: simple≤2, medium≤4, advanced≤12

## Leaderboard (ranked by correctness ↓)

| # | Model (experiment) | correctness | completeness | entity_cov | tool_calls | errors |
|---|---|---|---|---|---|---|
| 1 | `ollama-deepseek-v4-flash-cloud-v5-v5-smoke-0d1a4aee` | 0.967 | 1.0 | 0.7 | 2.133 | 0 |

## Per-tier breakdown

A single global tool_calls figure penalises the advanced tier by construction — it has a higher floor by design.

### `ollama-deepseek-v4-flash-cloud-v5-v5-smoke-0d1a4aee`

| tier | n | correctness | completeness | entity_cov | tool_calls | budget |
|---|---|---|---|---|---|---|
| simple | 15 | 0.967 | 1.0 | 0.7 | 2.133 | ≤2 |

## Per-question detail

### `ollama-deepseek-v4-flash-cloud-v5-v5-smoke-0d1a4aee`

| question | tier | correctness | completeness | entity_cov | tool_calls | over | err |
|---|---|---|---|---|---|---|---|
| How many devices belong to tenant Dunder-Mifflin, Inc.? | simple | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| Which rack holds device hq-acc04, and at which rack uni | simple | 1.0 | 1.0 | 1.0 | 1.0 |  |  |
| Device hq-acc02 has cabling recorded against it in NetB | simple | 1.0 | 1.0 | 1.0 | 1.0 |  |  |
| List the names of every device at site HVL-POR-BR02. | simple | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| How many IP prefixes are scoped to site HVL-SEA-HQ? | simple | 1.0 | 1.0 | 0.0 | 2.0 |  |  |
| What serial number is recorded for device sea-dc1-leaf0 | simple | 1.0 | 1.0 | 1.0 | 1.0 |  |  |
| How many sites belong to tenant Dunder-Mifflin, Inc.? | simple | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| How many circuits does provider Evergreen Networks supp | simple | 1.0 | 1.0 | 1.0 | 3.0 | ⚠ |  |
| Which devices belonging to tenant Dunder-Mifflin, Inc.  | simple | 1.0 | 1.0 | 0.0 | 2.0 |  |  |
| Is rack DC1-R04 empty, or does it hold mounted devices? | simple | 1.0 | 1.0 | 0.5 | 2.0 |  |  |
| List the names of every rack at site HVL-SEA-DC1. | simple | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| Which sites belonging to tenant Dunder-Mifflin, Inc. ha | simple | 1.0 | 1.0 | 1.0 | 5.0 | ⚠ |  |
| Does cluster HVL-SEA-HQ-EDGE have any virtual machines  | simple | 1.0 | 1.0 | 0.0 | 2.0 |  |  |
| How many Dunder-Mifflin sites have a VLAN with VID 100  | simple | 1.0 | 1.0 | 0.0 | 3.0 | ⚠ |  |
| How many devices are recorded at site HVL-SEA-DC1? Incl | simple | 0.5 | 1.0 | 1.0 | 2.0 |  |  |
