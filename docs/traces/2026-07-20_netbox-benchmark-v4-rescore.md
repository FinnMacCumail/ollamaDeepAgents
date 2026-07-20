# netbox-benchmark-v4 re-score of the v3 answers — 2026-07-20 14:37 UTC

Re-scoring the **stored 2026-07-05 v3 answers** (no agent reruns) with the new reference-grounded `correctness_judge`, which reads `reference_answer` and flags factual contradictions. v3's evaluators never read the reference, so completeness over-rewarded confident hallucinations. Ground truth re-verified vs live NetBox 2026-07-20 (DM Data prefix 10.112.149.0/24 = 0 IPs; all 180 NetBox IPs are in 172.16.0.0/24 → 0% allocation).

## Per-model: old completeness vs new correctness (mean over 6 questions)

| Model | old completeness | new correctness | Δ |
|---|---|---|---|
| `deepseek-v4-pro` | 0.717 | 0.833 | 0.116 |
| `glm-5` | 0.725 | 0.667 | -0.058 |
| `deepseek-v4-flash` | 0.8 | 0.583 | -0.217 |
| `kimi-k2.6` | 0.667 | 0.5 | -0.167 |
| `nemotron-3-ultra` | 0.733 | 0.5 | -0.233 |
| `qwen3.5-397b` | 0.583 | 0.417 | -0.166 |
| `minimax-m3` | 0.717 | 0.417 | -0.3 |
| `gpt-oss-120b` | 0.25 | 0.25 | 0.0 |
| `nemotron-3-super` | 0.25 | 0.167 | -0.083 |

## False positives — high completeness, low correctness

Rows where the old pipeline scored the answer complete (≥0.7) but it factually contradicts the verified reference (correctness ≤0.5). These are the hallucinations the v3 harness could not see.

| Model | category | old comp | new corr | contradiction |
|---|---|---|---|---|
| `qwen3.5-397b` | site-comparison | 1.0 | 0.0 | Model claims 17.58% IP utilization, but reference says 0% utilization. |
| `minimax-m3` | multi-site-vlan | 1.0 | 0.0 | Model claims 1,586 interfaces use VLAN 100, but reference says no interfaces are configure |
| `deepseek-v4-flash` | site-comparison | 0.9 | 0.0 | Model claims ~7.7% IP utilization and 180 IPs allocated, contradicting reference's 0% util |
| `glm-5` | site-comparison | 0.85 | 0.0 | Model claims 17.6% IP utilization, but reference states 0% utilization (no host IPs alloca |
| `minimax-m3` | site-comparison | 0.8 | 0.0 | Model claims 100% IP allocation per /22, whereas reference states 0% utilization (no host  |
| `nemotron-3-ultra` | rack-inventory | 1.0 | 0.5 | Model claims a link from ncsu128-distswitch1 to ncsu-coreswitch1, whereas reference states |
| `nemotron-3-ultra` | site-comparison | 0.9 | 0.5 | Model claims 4 devices per site and 4 /24 prefixes (180 IPs) while reference states 3 tena |
| `deepseek-v4-flash` | multi-site-vlan | 0.9 | 0.5 | The VLAN ID column incorrectly lists 1,3,5,… instead of 100, contradicting the reference t |
| `deepseek-v4-pro` | site-comparison | 0.8 | 0.5 | Model claims <2% IP utilization, contradicting reference's 0% utilization. |

## Full per-question detail

### `deepseek-v4-pro`

| category | old comp | old entity | new correctness | note |
|---|---|---|---|---|
| multi-site-vlan | 1.0 | 1.0 | 1.0 | All claims in the model answer agree with the reference; no contradictions are p |
| site-comparison | 0.8 | 0.8333 | 0.5 | Model claims <2% IP utilization, contradicting reference's 0% utilization. |
| negative-finding-vlan | 1.0 | 1.0 | 1.0 | All claims agree with reference; no contradictions. |
| tenant-site-summary | 0.0 | 0.8 | 0.5 | Model states 4 devices per site, whereas reference specifies only 3 tenant‑owned |
| device-detail | 0.5 | 0.8889 | 1.0 | All factual claims in the model answer agree with the reference; the only omissi |
| rack-inventory | 1.0 | 0.8889 | 1.0 | All factual claims in the model answer match the reference answer; no contradict |

### `glm-5`

| category | old comp | old entity | new correctness | note |
|---|---|---|---|---|
| multi-site-vlan | 0.0 | 0.8947 | 1.0 | All factual claims in the model answer match the reference answer; no contradict |
| site-comparison | 0.85 | 0.8333 | 0.0 | Model claims 17.6% IP utilization, but reference states 0% utilization (no host  |
| negative-finding-vlan | 1.0 | 1.0 | 1.0 | All factual claims in the model answer agree with the reference; no contradictio |
| tenant-site-summary | 0.5 | 0.85 | 0.0 | Model answer states 4 devices and 5 prefixes per branch site, but reference says |
| device-detail | 1.0 | 1.0 | 1.0 | All factual claims in the model answer agree with the reference answer; no contr |
| rack-inventory | 1.0 | 1.0 | 1.0 | All factual claims in the model answer match the reference answer; no contradict |

### `deepseek-v4-flash`

| category | old comp | old entity | new correctness | note |
|---|---|---|---|---|
| multi-site-vlan | 0.9 | 1.0 | 0.5 | The VLAN ID column incorrectly lists 1,3,5,… instead of 100, contradicting the r |
| site-comparison | 0.9 | 0.8333 | 0.0 | Model claims ~7.7% IP utilization and 180 IPs allocated, contradicting reference |
| negative-finding-vlan | 1.0 | 1.0 | 1.0 | All claims about Jimbob's sites match the reference; no contradictions. |
| tenant-site-summary | 0.5 | 0.85 | 0.0 | Model claims all 14 sites are active with 4 devices each, whereas reference stat |
| device-detail | 0.5 | 0.8889 | 1.0 | All factual claims match the reference; no contradictions are present. |
| rack-inventory | 1.0 | 1.0 | 1.0 | All factual claims in the model answer match the reference answer; no contradict |

### `kimi-k2.6`

| category | old comp | old entity | new correctness | note |
|---|---|---|---|---|
| multi-site-vlan | 0.0 | 0.8947 | 0.0 | Model claims devices are configured on VLAN 100, but reference states no interfa |
| site-comparison | 0.5 | 0.8333 | 0.0 | Model claims ~17.6% IP utilization and 180 allocated IPs, contradicting referenc |
| negative-finding-vlan | 1.0 | 1.0 | 1.0 | All claims about VLAN 100 match the reference; additional details about other VL |
| tenant-site-summary | 0.5 | 0.75 | 0.0 | Model answer lists 52 devices, 65 prefixes, and 42 VLANs, whereas reference stat |
| device-detail | 1.0 | 0.8889 | 1.0 | All factual claims in the model answer agree with the reference; no contradictio |
| rack-inventory | 1.0 | 0.8889 | 1.0 | All factual claims in the model answer match the reference; no contradictions fo |

### `nemotron-3-ultra`

| category | old comp | old entity | new correctness | note |
|---|---|---|---|---|
| multi-site-vlan | 0.0 | 0.8421 | 0.0 | Model claims VLAN 100 has devices and 180 allocated IPs, but reference says no i |
| site-comparison | 0.9 | 0.8333 | 0.5 | Model claims 4 devices per site and 4 /24 prefixes (180 IPs) while reference sta |
| negative-finding-vlan | 1.0 | 0.75 | 1.0 | All claims agree with reference; no contradictions. |
| tenant-site-summary | 0.5 | 0.8 | 0.0 | Model claims 4 devices per site (52 total) and 5 prefixes per site (65 total), w |
| device-detail | 1.0 | 1.0 | 1.0 | All factual claims in the model answer agree with the reference answer; no contr |
| rack-inventory | 1.0 | 1.0 | 0.5 | Model claims a link from ncsu128-distswitch1 to ncsu-coreswitch1, whereas refere |

### `qwen3.5-397b`

| category | old comp | old entity | new correctness | note |
|---|---|---|---|---|
| multi-site-vlan | 0.0 | 0.8421 | 0.0 | Model claims 180 IP addresses allocated to VLAN 100, contradicting reference tha |
| site-comparison | 1.0 | 1.0 | 0.0 | Model claims 17.58% IP utilization, but reference says 0% utilization. |
| negative-finding-vlan | 0.5 | 1.0 | 1.0 | All factual claims in the model answer agree with the reference; no contradictio |
| tenant-site-summary | 0.5 | 0.75 | 0.0 | Model claims 4 devices and 5 IP prefixes per site (vs 3 each in reference) and t |
| device-detail | 1.0 | 1.0 | 1.0 | All factual claims match the reference; no contradictions. |
| rack-inventory | 0.5 | 1.0 | 0.5 | Model claims the distribution switch has PSU connections (PSU0, PSU1), whereas t |

### `minimax-m3`

| category | old comp | old entity | new correctness | note |
|---|---|---|---|---|
| multi-site-vlan | 1.0 | 0.9474 | 0.0 | Model claims 1,586 interfaces use VLAN 100, but reference says no interfaces are |
| site-comparison | 0.8 | 0.8333 | 0.0 | Model claims 100% IP allocation per /22, whereas reference states 0% utilization |
| negative-finding-vlan | 0.5 | 0.5 | 1.0 | All claims in the model answer agree with the reference; no contradictions or fa |
| tenant-site-summary | 0.5 | 0.8 | 0.0 | Model claims 4 devices per branch site, but reference states only 3 tenant-owned |
| device-detail | 0.5 | 0.8889 | 0.5 | Model answer incorrectly states the device has no location assigned, contradicti |
| rack-inventory | 1.0 | 1.0 | 1.0 | All factual claims in the model answer match the reference; no contradictions fo |

### `gpt-oss-120b`

| category | old comp | old entity | new correctness | note |
|---|---|---|---|---|
| multi-site-vlan | 0.5 | 0.8421 | 0.5 | The model incorrectly lists VLAN IDs as 1,3,5,… instead of 100, contradicting th |
| site-comparison | 0.0 | 0.1667 | 0.0 | Model answer provides only a query, not the requested counts, statuses, or IP ut |
| negative-finding-vlan | 1.0 | 0.25 | 1.0 | The model correctly states that VLAN 100 is not present on any Jimbob’s Banking  |
| tenant-site-summary | 0.0 | 0.0 | 0.0 | ERROR Empty answer |
| device-detail | 0.0 | 0.5556 | 0.0 | Model claims 180 IP addresses assigned and no rack position, whereas reference s |
| rack-inventory | 0.0 | 0.0 | 0.0 | ERROR Empty answer |

### `nemotron-3-super`

| category | old comp | old entity | new correctness | note |
|---|---|---|---|---|
| multi-site-vlan | 0.5 | 0.7368 | 0.0 | Model answer claims devices and IP allocations for VLAN 100, whereas reference s |
| site-comparison | 0.5 | 0.6667 | 0.0 | Model claims 4 devices per site (1 without tenant) and that IP allocation is unk |
| negative-finding-vlan | 0.0 | 0.0 | 0.0 | Empty answer |
| tenant-site-summary | 0.0 | 0.0 | 0.0 | ERROR Empty answer |
| device-detail | 0.0 | 0.3333 | 1.0 | No contradictions with the reference; the answer omits rack and tenant details b |
| rack-inventory | 0.5 | 0.7778 | 0.0 | Model claims 48 active power feeds for each device, but reference states there a |
