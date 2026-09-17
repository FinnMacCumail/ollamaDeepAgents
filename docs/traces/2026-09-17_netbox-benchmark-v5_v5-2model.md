# netbox-benchmark-v5 [v5-2model] — 2026-09-17 13:13 UTC

- Dataset: **netbox-benchmark-v5** (90 examples)
- Evaluators: entity_coverage · completeness · tool_calls · **correctness**
- Tool-call budgets: simple≤2, medium≤7, advanced≤12

## Leaderboard (ranked by correctness ↓)

| # | Model (experiment) | correctness | completeness | entity_cov | tool_calls | errors |
|---|---|---|---|---|---|---|
| 1 | `ollama-deepseek-v4-pro-cloud-v5-v5-2model-a732d63c` | 0.933 | 0.944 | 0.831 | 4.933 | 0 |
| 2 | `ollama-deepseek-v4-flash-cloud-v5-v5-2model-c60059b2` | 0.906 | 0.956 | 0.885 | 6.267 | 0 |

## Per-tier breakdown

A single global tool_calls figure penalises the advanced tier by construction — it has a higher floor by design.

### `ollama-deepseek-v4-pro-cloud-v5-v5-2model-a732d63c`

| tier | n | correctness | completeness | entity_cov | tool_calls | budget |
|---|---|---|---|---|---|---|
| simple | 30 | 0.983 | 0.983 | 0.935 | 3.467 | ≤2 |
| medium | 30 | 0.967 | 0.983 | 0.875 | 4.733 | ≤7 |
| advanced | 30 | 0.85 | 0.867 | 0.704 | 6.6 | ≤12 |

### `ollama-deepseek-v4-flash-cloud-v5-v5-2model-c60059b2`

| tier | n | correctness | completeness | entity_cov | tool_calls | budget |
|---|---|---|---|---|---|---|
| simple | 30 | 0.967 | 0.983 | 0.957 | 4.0 | ≤2 |
| medium | 30 | 0.95 | 0.983 | 0.875 | 6.2 | ≤7 |
| advanced | 30 | 0.8 | 0.9 | 0.833 | 8.6 | ≤12 |

## Per-question detail

### `ollama-deepseek-v4-pro-cloud-v5-v5-2model-a732d63c`

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
| How many devices are recorded at site HVL-SEA-DC1? Incl | simple | 0.5 | 1.0 | 1.0 | 2.0 |  |  |
| How many IP prefixes are scoped to site HVL-SEA-HQ? | simple | 1.0 | 1.0 | None | 2.0 |  |  |
| Is rack DC1-R04 empty, or does it hold mounted devices? | simple | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| Does cluster HVL-SEA-HQ-EDGE have any virtual machines  | simple | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| How many Dunder-Mifflin sites have a VLAN with VID 100  | simple | 1.0 | 0.5 | 0.0 | 1.0 |  |  |
| Which devices belonging to tenant Dunder-Mifflin, Inc.  | simple | 1.0 | 1.0 | None | 3.0 | ⚠ |  |
| An active Halvorsen Logistics prefix is nested inside a | advanced | 1.0 | 1.0 | 1.0 | 6.0 |  |  |
| Across the whole instance, how many devices carry no te | advanced | 0.0 | 0.5 | 0.0 | 4.0 |  |  |
| Which Halvorsen Logistics circuit has a decommissioned  | advanced | 1.0 | 1.0 | 1.0 | 12.0 |  |  |
| One Halvorsen Logistics cable has lost the equipment on | advanced | 1.0 | 1.0 | 1.0 | 12.0 |  |  |
| Comparing the two tenants that own circuits, does Dunde | advanced | 1.0 | 1.0 | 1.0 | 5.0 |  |  |
| Counting every site in the instance regardless of tenan | advanced | 0.5 | 0.5 | 1.0 | 1.0 |  |  |
| One Halvorsen Logistics IP address carries a mask that  | advanced | 1.0 | 1.0 | 1.0 | 4.0 |  |  |
| Which VLAN group has the highest utilization figure rec | advanced | 0.0 | 1.0 | 1.0 | 1.0 |  |  |
| The uplink on hq-acc04 does not reach its distribution  | advanced | 1.0 | 1.0 | 0.0 | 11.0 |  |  |
| Is there any Halvorsen Logistics site that has no route | advanced | 1.0 | 1.0 | None | 7.0 |  |  |
| Some Halvorsen Logistics IP addresses sit outside every | advanced | 1.0 | 1.0 | 1.0 | 12.0 |  |  |
| Do any Halvorsen Logistics branch sites have a firewall | advanced | 1.0 | 1.0 | 1.0 | 4.0 |  |  |
| Each Halvorsen Logistics hypervisor host has two power  | advanced | 1.0 | 1.0 | 1.0 | 16.0 | ⚠ |  |
| Counting only devices that carry the NC State Universit | advanced | 1.0 | 0.5 | 0.0 | 5.0 |  |  |
| How many Halvorsen Logistics virtual machines have no p | advanced | 1.0 | 1.0 | 1.0 | 6.0 |  |  |
| Which access switches at site HVL-SEA-HQ are in the act | medium | 1.0 | 1.0 | 1.0 | 3.0 |  |  |
| Excluding patch panels and PDUs, which active Halvorsen | medium | 1.0 | 1.0 | 1.0 | 5.0 |  |  |
| Excluding patch panels and PDUs, which Halvorsen Logist | medium | 1.0 | 1.0 | 1.0 | 4.0 |  |  |
| At site HVL-SEA-DC1, which rack holds the most mounted  | medium | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| Which Halvorsen Logistics circuits are not in the activ | medium | 1.0 | 1.0 | 1.0 | 9.0 | ⚠ |  |
| Which Halvorsen Logistics hypervisor hosts have no virt | medium | 1.0 | 1.0 | 1.0 | 13.0 | ⚠ |  |
| Do the Halvorsen Logistics branch sites have power pane | medium | 1.0 | 1.0 | 1.0 | 4.0 |  |  |
| Ignoring wireless access points, which Halvorsen Logist | medium | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| No device at site HVL-BOI-BR04 appears in a list of act | medium | 1.0 | 1.0 | 1.0 | 3.0 |  |  |
| Which IP addresses are assigned inside the VRF named HV | medium | 1.0 | 1.0 | None | 9.0 | ⚠ |  |
| Which VRFs contain exactly 30 IP addresses each? List t | medium | 1.0 | 1.0 | 1.0 | 3.0 |  |  |
| Which providers supply circuits to tenant Dunder-Miffli | medium | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| In the NetBox change log, compare these four object typ | medium | 1.0 | 1.0 | None | 6.0 |  |  |
| Which sites belonging to tenant Dunder-Mifflin, Inc. ha | medium | 1.0 | 1.0 | 1.0 | 3.0 |  |  |
| How many devices sitting at Dunder-Mifflin sites are no | medium | 1.0 | 1.0 | 1.0 | 12.0 | ⚠ |  |
| Do all tenants in NetBox have at least one site? Name a | advanced | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| NetBox has two tenant groups. Which one holds the most  | simple | 1.0 | 1.0 | 1.0 | 1.0 |  |  |
| Which change-log action is recorded least often across  | medium | 1.0 | 1.0 | 0.0 | 12.0 | ⚠ |  |
| The change log holds 22 deletion records. What single e | advanced | 0.0 | 0.0 | 1.0 | 1.0 |  |  |
| Are all Halvorsen Logistics virtual machines in the act | medium | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| Which circuit type is used by the most circuits in NetB | medium | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| How many change-log records does NetBox hold for device | simple | 1.0 | 1.0 | None | 3.0 | ⚠ |  |
| How many Halvorsen Logistics prefixes have no VLAN asso | medium | 1.0 | 1.0 | None | 2.0 |  |  |
| Which virtualization platform does cluster HVL-SEA-HQ-E | simple | 1.0 | 1.0 | 1.0 | 1.0 |  |  |
| Outside the data-centre VLAN group, do any Halvorsen Lo | advanced | 1.0 | 1.0 | None | 5.0 |  |  |
| Which power feeds does panel DC1-PP-A supply? List them | simple | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| What is the total vCPU count across all Halvorsen Logis | advanced | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| Which Halvorsen Logistics power feeds are not in the ac | medium | 1.0 | 1.0 | 1.0 | 4.0 |  |  |
| The power feeds at HVL-SEA-DC1 and those at HVL-SEA-HQ  | advanced | 1.0 | 0.5 | 0.0 | 4.0 |  |  |
| Which circuits in NetBox are of the Point-to-point circ | simple | 1.0 | 1.0 | None | 4.0 | ⚠ |  |
| Which user account is recorded as having made the chang | simple | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| Two rack reservations block capacity in the Halvorsen d | advanced | 1.0 | 1.0 | 1.0 | 10.0 |  |  |
| How many rack reservations exist in NetBox, and how man | simple | 1.0 | 1.0 | None | 3.0 | ⚠ |  |
| Comparing the power feeds at the Halvorsen data centre  | advanced | 1.0 | 1.0 | 0.0 | 11.0 |  |  |
| Which tenant is the only one in NetBox that owns virtua | simple | 1.0 | 1.0 | 1.0 | 3.0 | ⚠ |  |
| How many power outlets does each Halvorsen Logistics PD | simple | 1.0 | 1.0 | 0.5 | 17.0 | ⚠ |  |
| Which Halvorsen Logistics PDUs have any outlet in use,  | medium | 1.0 | 1.0 | 1.0 | 4.0 |  |  |
| NC State University and Jimbob's Banking & Trust are bo | advanced | 0.0 | 0.5 | 0.0 | 11.0 |  |  |
| Outside the Halvorsen data centre, is any rack anywhere | advanced | 1.0 | 1.0 | 1.0 | 6.0 |  |  |
| Do any Halvorsen Logistics PDUs draw power from a model | medium | 1.0 | 1.0 | 0.0 | 13.0 | ⚠ |  |
| One tenant has VLANs defined but owns no devices, racks | medium | 1.0 | 1.0 | 1.0 | 3.0 |  |  |
| Which single circuit has the most change-log records, h | advanced | 1.0 | 1.0 | 1.0 | 7.0 |  |  |
| Across the whole change log, which action accounts for  | medium | 1.0 | 1.0 | None | 3.0 |  |  |
| Which IP aggregates are registered under RFC 1918, and  | medium | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| Which contacts are attached to site DM-Scranton, and wh | medium | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| Which operating-system platforms are recorded on Halvor | advanced | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| Do all Halvorsen Logistics circuits have two terminatio | simple | 1.0 | 1.0 | 1.0 | 8.0 | ⚠ |  |
| NetBox holds a large number of Google Cloud clusters. D | advanced | 1.0 | 0.5 | 0.0 | 11.0 |  |  |
| Are there any tenants in NetBox that belong to neither  | advanced | 1.0 | 1.0 | None | 2.0 |  |  |
| Most singly-terminated circuits in NetBox are internet- | advanced | 1.0 | 1.0 | 1.0 | 12.0 |  |  |
| Which prefixes belonging to Halvorsen Logistics have no | medium | 1.0 | 1.0 | None | 7.0 |  |  |
| How much total disk is provisioned across all Halvorsen | medium | 0.0 | 1.0 | None | 3.0 |  |  |
| Which contacts are assigned the Billing role in NetBox? | simple | 1.0 | 1.0 | None | 4.0 | ⚠ |  |
| Which user accounts other than seeder appear against en | simple | 1.0 | 1.0 | None | 14.0 | ⚠ |  |
| Do any Halvorsen Logistics virtual machines have a role | medium | 1.0 | 0.5 | 0.0 | 2.0 |  |  |
| How many Halvorsen Logistics virtual machines have no n | simple | 1.0 | 1.0 | 1.0 | 5.0 | ⚠ |  |
| According to the change log, was any Halvorsen Logistic | advanced | 1.0 | 1.0 | 0.0 | 6.0 |  |  |
| Across all Halvorsen Logistics PDUs, how many of the av | simple | 1.0 | 1.0 | 1.0 | 6.0 | ⚠ |  |
| Which provider networks are defined in NetBox, and whic | medium | 1.0 | 1.0 | 1.0 | 1.0 |  |  |
| Which device platforms have at least one device assigne | simple | 1.0 | 1.0 | 1.0 | 2.0 |  |  |

### `ollama-deepseek-v4-flash-cloud-v5-v5-2model-c60059b2`

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
| Which sites belonging to tenant Dunder-Mifflin, Inc. ha | simple | 1.0 | 1.0 | 1.0 | 4.0 | ⚠ |  |
| How many devices are recorded at site HVL-SEA-DC1? Incl | simple | 1.0 | 0.5 | 1.0 | 2.0 |  |  |
| How many IP prefixes are scoped to site HVL-SEA-HQ? | simple | 1.0 | 1.0 | None | 2.0 |  |  |
| Is rack DC1-R04 empty, or does it hold mounted devices? | simple | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| Does cluster HVL-SEA-HQ-EDGE have any virtual machines  | simple | 1.0 | 1.0 | 1.0 | 3.0 | ⚠ |  |
| How many Dunder-Mifflin sites have a VLAN with VID 100  | simple | 1.0 | 1.0 | 1.0 | 3.0 | ⚠ |  |
| Which devices belonging to tenant Dunder-Mifflin, Inc.  | simple | 1.0 | 1.0 | None | 2.0 |  |  |
| An active Halvorsen Logistics prefix is nested inside a | advanced | 1.0 | 1.0 | 1.0 | 9.0 |  |  |
| Across the whole instance, how many devices carry no te | advanced | 0.0 | 0.5 | 0.0 | 8.0 |  |  |
| Which Halvorsen Logistics circuit has a decommissioned  | advanced | 1.0 | 1.0 | 1.0 | 17.0 | ⚠ |  |
| One Halvorsen Logistics cable has lost the equipment on | advanced | 1.0 | 1.0 | 1.0 | 13.0 | ⚠ |  |
| Comparing the two tenants that own circuits, does Dunde | advanced | 1.0 | 1.0 | 1.0 | 5.0 |  |  |
| Counting every site in the instance regardless of tenan | advanced | 1.0 | 1.0 | 1.0 | 3.0 |  |  |
| One Halvorsen Logistics IP address carries a mask that  | advanced | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| Which VLAN group has the highest utilization figure rec | advanced | 0.0 | 1.0 | 1.0 | 1.0 |  |  |
| The uplink on hq-acc04 does not reach its distribution  | advanced | 0.0 | 1.0 | 1.0 | 31.0 | ⚠ |  |
| Is there any Halvorsen Logistics site that has no route | advanced | 1.0 | 1.0 | None | 7.0 |  |  |
| Some Halvorsen Logistics IP addresses sit outside every | advanced | 1.0 | 1.0 | 1.0 | 16.0 | ⚠ |  |
| Do any Halvorsen Logistics branch sites have a firewall | advanced | 1.0 | 1.0 | 1.0 | 6.0 |  |  |
| Each Halvorsen Logistics hypervisor host has two power  | advanced | 1.0 | 1.0 | 1.0 | 22.0 | ⚠ |  |
| Counting only devices that carry the NC State Universit | advanced | 1.0 | 0.5 | 0.0 | 3.0 |  |  |
| How many Halvorsen Logistics virtual machines have no p | advanced | 1.0 | 1.0 | 1.0 | 5.0 |  |  |
| Which access switches at site HVL-SEA-HQ are in the act | medium | 1.0 | 1.0 | 1.0 | 8.0 | ⚠ |  |
| Excluding patch panels and PDUs, which active Halvorsen | medium | 1.0 | 1.0 | 1.0 | 11.0 | ⚠ |  |
| Excluding patch panels and PDUs, which Halvorsen Logist | medium | 0.0 | 1.0 | 1.0 | 7.0 |  |  |
| At site HVL-SEA-DC1, which rack holds the most mounted  | medium | 1.0 | 1.0 | 1.0 | 6.0 |  |  |
| Which Halvorsen Logistics circuits are not in the activ | medium | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| Which Halvorsen Logistics hypervisor hosts have no virt | medium | 1.0 | 1.0 | 1.0 | 17.0 | ⚠ |  |
| Do the Halvorsen Logistics branch sites have power pane | medium | 1.0 | 1.0 | 1.0 | 11.0 | ⚠ |  |
| Ignoring wireless access points, which Halvorsen Logist | medium | 1.0 | 1.0 | 1.0 | 5.0 |  |  |
| No device at site HVL-BOI-BR04 appears in a list of act | medium | 1.0 | 1.0 | 1.0 | 3.0 |  |  |
| Which IP addresses are assigned inside the VRF named HV | medium | 1.0 | 1.0 | None | 2.0 |  |  |
| Which VRFs contain exactly 30 IP addresses each? List t | medium | 1.0 | 1.0 | 1.0 | 9.0 | ⚠ |  |
| Which providers supply circuits to tenant Dunder-Miffli | medium | 0.5 | 1.0 | 1.0 | 4.0 |  |  |
| In the NetBox change log, compare these four object typ | medium | 1.0 | 1.0 | None | 6.0 |  |  |
| Which sites belonging to tenant Dunder-Mifflin, Inc. ha | medium | 1.0 | 1.0 | 1.0 | 5.0 |  |  |
| How many devices sitting at Dunder-Mifflin sites are no | medium | 1.0 | 1.0 | 1.0 | 15.0 | ⚠ |  |
| Do all tenants in NetBox have at least one site? Name a | advanced | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| NetBox has two tenant groups. Which one holds the most  | simple | 1.0 | 1.0 | 1.0 | 3.0 | ⚠ |  |
| Which change-log action is recorded least often across  | medium | 1.0 | 1.0 | 1.0 | 8.0 | ⚠ |  |
| The change log holds 22 deletion records. What single e | advanced | 0.0 | 0.0 | 1.0 | 1.0 |  |  |
| Are all Halvorsen Logistics virtual machines in the act | medium | 1.0 | 1.0 | 1.0 | 3.0 |  |  |
| Which circuit type is used by the most circuits in NetB | medium | 1.0 | 1.0 | 0.0 | 2.0 |  |  |
| How many change-log records does NetBox hold for device | simple | 1.0 | 1.0 | None | 2.0 |  |  |
| How many Halvorsen Logistics prefixes have no VLAN asso | medium | 1.0 | 1.0 | None | 2.0 |  |  |
| Which virtualization platform does cluster HVL-SEA-HQ-E | simple | 1.0 | 1.0 | 1.0 | 1.0 |  |  |
| Outside the data-centre VLAN group, do any Halvorsen Lo | advanced | 1.0 | 1.0 | None | 15.0 | ⚠ |  |
| Which power feeds does panel DC1-PP-A supply? List them | simple | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| What is the total vCPU count across all Halvorsen Logis | advanced | 1.0 | 1.0 | 1.0 | 6.0 |  |  |
| Which Halvorsen Logistics power feeds are not in the ac | medium | 1.0 | 1.0 | 1.0 | 7.0 |  |  |
| The power feeds at HVL-SEA-DC1 and those at HVL-SEA-HQ  | advanced | 1.0 | 1.0 | 1.0 | 4.0 |  |  |
| Which circuits in NetBox are of the Point-to-point circ | simple | 0.0 | 1.0 | None | 3.0 | ⚠ |  |
| Which user account is recorded as having made the chang | simple | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| Two rack reservations block capacity in the Halvorsen d | advanced | 0.0 | 0.0 | 0.0 | 7.0 |  |  |
| How many rack reservations exist in NetBox, and how man | simple | 1.0 | 1.0 | None | 3.0 | ⚠ |  |
| Comparing the power feeds at the Halvorsen data centre  | advanced | 1.0 | 1.0 | 0.0 | 17.0 | ⚠ |  |
| Which tenant is the only one in NetBox that owns virtua | simple | 1.0 | 1.0 | 1.0 | 3.0 | ⚠ |  |
| How many power outlets does each Halvorsen Logistics PD | simple | 1.0 | 1.0 | 0.0 | 21.0 | ⚠ |  |
| Which Halvorsen Logistics PDUs have any outlet in use,  | medium | 1.0 | 1.0 | 1.0 | 7.0 |  |  |
| NC State University and Jimbob's Banking & Trust are bo | advanced | 1.0 | 1.0 | 0.5 | 6.0 |  |  |
| Outside the Halvorsen data centre, is any rack anywhere | advanced | 1.0 | 1.0 | 1.0 | 8.0 |  |  |
| Do any Halvorsen Logistics PDUs draw power from a model | medium | 1.0 | 1.0 | 0.0 | 23.0 | ⚠ |  |
| One tenant has VLANs defined but owns no devices, racks | medium | 1.0 | 1.0 | 1.0 | 4.0 |  |  |
| Which single circuit has the most change-log records, h | advanced | 1.0 | 1.0 | 1.0 | 4.0 |  |  |
| Across the whole change log, which action accounts for  | medium | 1.0 | 1.0 | None | 3.0 |  |  |
| Which IP aggregates are registered under RFC 1918, and  | medium | 1.0 | 1.0 | 1.0 | 1.0 |  |  |
| Which contacts are attached to site DM-Scranton, and wh | medium | 1.0 | 1.0 | 1.0 | 2.0 |  |  |
| Which operating-system platforms are recorded on Halvor | advanced | 0.0 | 1.0 | 1.0 | 3.0 |  |  |
| Do all Halvorsen Logistics circuits have two terminatio | simple | 1.0 | 1.0 | 1.0 | 11.0 | ⚠ |  |
| NetBox holds a large number of Google Cloud clusters. D | advanced | 1.0 | 1.0 | 1.0 | 13.0 | ⚠ |  |
| Are there any tenants in NetBox that belong to neither  | advanced | 1.0 | 1.0 | None | 2.0 |  |  |
| Most singly-terminated circuits in NetBox are internet- | advanced | 1.0 | 1.0 | 1.0 | 17.0 | ⚠ |  |
| Which prefixes belonging to Halvorsen Logistics have no | medium | 1.0 | 1.0 | None | 7.0 |  |  |
| How much total disk is provisioned across all Halvorsen | medium | 1.0 | 1.0 | None | 2.0 |  |  |
| Which contacts are assigned the Billing role in NetBox? | simple | 1.0 | 1.0 | None | 4.0 | ⚠ |  |
| Which user accounts other than seeder appear against en | simple | 1.0 | 1.0 | None | 12.0 | ⚠ |  |
| Do any Halvorsen Logistics virtual machines have a role | medium | 1.0 | 0.5 | 0.0 | 3.0 |  |  |
| How many Halvorsen Logistics virtual machines have no n | simple | 1.0 | 1.0 | 1.0 | 10.0 | ⚠ |  |
| According to the change log, was any Halvorsen Logistic | advanced | 1.0 | 1.0 | 1.0 | 5.0 |  |  |
| Across all Halvorsen Logistics PDUs, how many of the av | simple | 1.0 | 1.0 | 1.0 | 8.0 | ⚠ |  |
| Which provider networks are defined in NetBox, and whic | medium | 1.0 | 1.0 | 1.0 | 1.0 |  |  |
| Which device platforms have at least one device assigne | simple | 1.0 | 1.0 | 1.0 | 3.0 | ⚠ |  |
