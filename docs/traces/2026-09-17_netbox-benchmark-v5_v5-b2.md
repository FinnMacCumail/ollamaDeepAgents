# netbox-benchmark-v5 [v5-b2] — 2026-09-17 09:50 UTC

- Dataset: **netbox-benchmark-v5** (30 examples)
- Evaluators: entity_coverage · completeness · tool_calls · **correctness**
- Tool-call budgets: simple≤2, medium≤4, advanced≤12

## Leaderboard (ranked by correctness ↓)

| # | Model (experiment) | correctness | completeness | entity_cov | tool_calls | errors |
|---|---|---|---|---|---|---|
| 1 | `ollama-deepseek-v4-flash-cloud-v5-v5-b2-fd9ecc94` | 1.0 | 0.983 | 0.964 | 4.833 | 0 |

## Per-tier breakdown

A single global tool_calls figure penalises the advanced tier by construction — it has a higher floor by design.

### `ollama-deepseek-v4-flash-cloud-v5-v5-b2-fd9ecc94`

| tier | n | correctness | completeness | entity_cov | tool_calls | budget |
|---|---|---|---|---|---|---|
| simple | 15 | 1.0 | 1.0 | 0.929 | 2.133 | ≤2 |
| medium | 15 | 1.0 | 0.967 | 1.0 | 7.533 | ≤4 |

## Per-question detail

### `ollama-deepseek-v4-flash-cloud-v5-v5-b2-fd9ecc94`

| question | tier | correctness | completeness | entity_cov | tool_calls | over | err |
|---|---|---|---|---|---|---|---|
| How many devices belong to tenant Dunder-Mifflin, Inc.? | simple | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| Which rack holds device hq-acc04, and at which rack uni | simple | 1.0 | 1.0 | 1.0 | 1.0 |  |  |
| Device hq-acc02 has cabling recorded against it in NetB | simple | 1.0 | 1.0 | 1.0 | 1.0 |  |  |
| List the names of every device at site HVL-POR-BR02. | simple | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| What serial number is recorded for device sea-dc1-leaf0 | simple | 1.0 | 1.0 | 1.0 | 1.0 |  |  |
| How many sites belong to tenant Dunder-Mifflin, Inc.? | simple | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| How many circuits does provider Evergreen Networks supp | simple | 1.0 | 1.0 | 1.0 | 3.0 | ⚠ |  |
| List the names of every rack at site HVL-SEA-DC1. | simple | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| Which sites belonging to tenant Dunder-Mifflin, Inc. ha | simple | 1.0 | 1.0 | 1.0 | 3.0 | ⚠ |  |
| How many devices are recorded at site HVL-SEA-DC1? Incl | simple | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| How many IP prefixes are scoped to site HVL-SEA-HQ? | simple | 1.0 | 1.0 | None | 2.0 |  |  |
| Is rack DC1-R04 empty, or does it hold mounted devices? | simple | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| Does cluster HVL-SEA-HQ-EDGE have any virtual machines  | simple | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| Which devices belonging to tenant Dunder-Mifflin, Inc.  | simple | 1.0 | 1.0 | 0.0 | 2.0 |  |  |
| How many Dunder-Mifflin sites have a VLAN with VID 100  | simple | 1.0 | 1.0 | 1.0 | 5.0 | ⚠ |  |
| Which VRFs contain exactly 30 IP addresses each? List t | medium | 1.0 | 0.5 | 1.0 | 9.0 | ⚠ |  |
| Excluding patch panels and PDUs, which Halvorsen Logist | medium | 1.0 | 1.0 | 1.0 | 4.0 |  |  |
| Which IP addresses are assigned inside the VRF named HV | medium | 1.0 | 1.0 | None | 2.0 |  |  |
| Excluding patch panels and PDUs, which active Halvorsen | medium | 1.0 | 1.0 | 1.0 | 17.0 | ⚠ |  |
| Across the whole NetBox instance, changes to which obje | medium | 1.0 | 1.0 | 1.0 | 29.0 | ⚠ |  |
| Ignoring wireless access points, which Halvorsen Logist | medium | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| Which Halvorsen Logistics hypervisor hosts have no virt | medium | 1.0 | 1.0 | 1.0 | 5.0 | ⚠ |  |
| Which Halvorsen Logistics circuits are not in the activ | medium | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| Which sites belonging to tenant Dunder-Mifflin, Inc. ha | medium | 1.0 | 1.0 | 1.0 | 5.0 | ⚠ |  |
| Which providers supply circuits to tenant Dunder-Miffli | medium | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| How many devices sitting at Dunder-Mifflin sites are no | medium | 1.0 | 1.0 | 1.0 | 19.0 | ⚠ |  |
| Do the Halvorsen Logistics branch sites have power pane | medium | 1.0 | 1.0 | 1.0 | 4.0 |  |  |
| At site HVL-SEA-DC1, which rack holds the most mounted  | medium | 1.0 | 1.0 | 1.0 | 6.0 | ⚠ |  |
| No device at site HVL-BOI-BR04 appears in a list of act | medium | 1.0 | 1.0 | 1.0 | 3.0 |  |  |
| Which access switches at site HVL-SEA-HQ are in the act | medium | 1.0 | 1.0 | 1.0 | 4.0 |  |  |
