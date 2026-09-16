# NetBox Data Enrichment for netbox-benchmark-v5 — Research

**Date:** 2026-09-15
**Status:** ✅ Research complete — no data changed; enrichment not started (decisions in §9)
**Purpose:** Establish, from the *live* instance, what the current NetBox data can and cannot support for
the v5 benchmark, and specify what must be enriched, how, and safely.
**Related:** `2026-09-15_netbox-benchmark-v5-expansion-design.md` (the v5 spec; its Part 4 "data-enrichment
prerequisite" is detailed here) · `tests/eval/dataset_v3.py` / `dataset_v4.py` (v4 references this must not
break) · `2026-08-10_langchain-ecosystem-vs-netbox-cloud-platform.md`.
**Method:** (1) read-only audit of the live instance via REST (GET only; scripts in session scratchpad);
(2) two online research threads — enrichment tooling for NetBox 4.3, and realistic NetOps dataset shape
(NetBox docs + v4.3 source, NetBox Labs *Zero to Hero*, netbox-community repos). One research thread also
counted rows in the published `netbox-demo-v4.3.sql`; its counts match the live audit exactly.

---

## TL;DR

- The instance is an **unmodified load of the official NetBox v4.3 demo dump**. It is rich in *inventory*
  (72 devices, 1,586 interfaces, 29 circuits, 180 VMs), but almost **none of the relationships advanced
  queries depend on are populated**:
  - **0/72 devices with a primary IP**
  - **0/180 IPs assigned to an interface**
  - **62/69 active prefixes empty**
  - **0 interface VLAN assignments**
  - **0/180 VMs with vCPU, memory or disk**
  - **0 change-log rows**
  - 100% of devices, VMs and circuits `active`
- Against the v5 coverage checklist (22 archetypes): **most SIMPLE/MEDIUM archetypes are answerable today;
  only ~3 of 10 ADVANCED ones are.** The rest are either *impossible* (no data) or *degenerate* (the answer
  is "all"/"none"/"0%" for everything, which tests nothing).
- **Recommended strategy: additive enrichment.** Add a new, fully-modelled tenant/region ("Halvorsen
  Logistics", ~6 sites / ~74 devices / ~200 IPs / ~250 cables / 14 circuits / 30 VMs) in unused address
  space, with a **written answer key of 17 deliberate defects**. Leave the demo objects untouched, so the
  v4 references stay valid.
  - Seed with an idempotent **pynetbox 7.5.0** REST script (the API path is the only one that populates the
    change log).
  - Pin the benchmark to a **`pg_dump -Fc` snapshot**, not to re-running the seed.
  - Compute gold answers **by script** against the snapshot.
- **Does this satisfy v5? Yes — conditionally (§5.1).** Coverage (all 22 archetypes) and volume (~45–60
  ADVANCED candidates vs the 30–50 target) are met. The binding condition: **tiers must cross both data
  islands**, or the tenant name becomes a proxy for difficulty and the routing benchmark can be gamed.
- **Four prerequisites before any write:**
  1. ✅ **Done (2026-09-16):** repaired the corrupted job-queue Valkey; the worker is running and
     `/api/status/` returns 200 again.
  2. Set `CHANGELOG_RETENTION=0` (the default 90 days would silently delete seeded history).
  3. Take a baseline snapshot of today's data.
  4. ✅ **Done (2026-09-16):** the agent now uses a dedicated read-only token (`write_enabled=false`,
     view-only permissions). A seeder token with write access is still to be provisioned at seed time.

---

## 1. Current state — live audit (2026-09-15)

**Instance:**

| Item | Value |
|---|---|
| NetBox | 4.3.3 on netbox-docker 3.3.0 (compose project `/home/ola/netbox-docker`) |
| Database | Postgres 17, `netbox`, **29 MB** |
| Data source | `netbox-community/netbox-demo-data` `sql/netbox-demo-v4.3.sql` (commit `6b43013`, 2025-05-02), cloned at `/home/ola/dev/netboxdev/netbox-demo-data` |
| Upstream | NetBox 4.7.0 is current; the demo repo ships dumps up to v4.7 |

**Object counts:**

| App | Counts |
|---|---|
| DCIM | 24 sites · 67 regions · 3 site groups · 4 locations · 42 racks · 2 rack reservations · 14 manufacturers · 14 device types · 9 device roles · 3 platforms · **72 devices** · 4 modules · 4 virtual chassis · **1,586 interfaces** · 912 front ports · 630 rear ports · 41 console ports · **0 console-server ports** · 75 power ports · 104 power outlets · 4 power panels · 48 power feeds · **108 cables** · **0 inventory items** · **0 MAC addresses** |
| IPAM | 4 aggregates · 8 RIRs · 90 prefixes (69 active, 21 container) · 4 IP ranges · **180 IPs** · 63 VLANs · 7 VLAN groups · 6 VRFs · 12 route targets · 5 ASNs · **0 services** · **0 FHRP groups** |
| Circuits | 9 providers (3 used) · 29 circuits · 45 terminations (32 to sites, 13 to provider networks) · 1 provider network · 0 provider accounts |
| Tenancy | 11 tenants (**only 3 have any data**) · 3 contacts · 3 contact assignments |
| Virtualization | 32 clusters (**23 empty**) · 180 VMs · 720 VM interfaces · **0 virtual disks** |
| Other | **0** wireless · **0** VPN · 26 tags · 1 custom field (`cust_id`) · **0** config contexts · **0** journal entries · **0 change-log rows** |

**Relationship density — the part that matters for advanced queries:**

| Relationship | Live value | Consequence |
|---|---|---|
| Devices with primary IP | **0 / 72** | "devices without a primary IP" = all of them (degenerate) |
| IPs assigned to an interface | **0 / 180** | device-by-IP, IPs-per-device, and interfaces-without-IP are all impossible or degenerate |
| Where the IPs are | all in 6 generic, unscoped, tenant-less /24s (172.16–20.0/24, 192.168.0.0/24) inside VRFs Alpha–Echo | none in any site's prefixes |
| Active prefixes with ≥1 IP | **7 / 69** (all generic); the 62 site prefixes are empty | "IP utilization %" = 0% everywhere a site question would look |
| Interface VLAN assignments | **0** (no access or tagged modes) | "which devices/interfaces carry VLAN N" = none (degenerate) |
| Interfaces cabled | 102 / 1,586 (6.4%); 0 console cables | thin, but some traces exist |
| Cable paths | 141 complete / 13 incomplete (from dump row count). Live sample trace: `dmi01-akron-rtr01:Gi0/0/0 → circuit KKDG4923 → Level3 MPLS` | circuit traces work; no multi-hop interface↔interface patch-panel path to a far device |
| Power | 4 panels, all at the NCSU MDF; **0/48 feeds cabled**; 26 PDU-outlet → device legs (DM branches) | panel → feed → PDU → device chain is broken at the feed |
| Circuits | CenturyLink 13 (internet, single-ended), Level 3 13 (MPLS, A+Z), NCSU Facilities 3 (dark fibre, A+Z); all active; 0 commit rates | **usable today** for "circuits per provider / where they terminate" |
| Rack fill | 24 racks occupied, 18 empty; used-U spread 2–16 U | **usable today** for free-RU questions (limited variety) |
| VMs | 0 vCPU/memory/disk; 0 site; 0 primary IP; all active; 9 clusters × 20 VMs, 23 clusters empty; clusters unscoped | cluster/VM resource and status questions are degenerate |
| Lifecycle statuses | 100% active (devices, VMs, circuits); prefixes only active/container | status-filter and audit questions have no variety |
| Device metadata | 0 serial numbers, 0 asset tags; 13/72 with a platform | serial/asset lookups impossible |
| Tenancy coverage | Dunder-Mifflin: 14 sites / 39 devices / 68 prefixes / 39 VLANs / 26 circuits / **0 IPs**. NC State: 4 sites / 29 racks / 19 devices / 3 circuits. Jimbob's: 6 sites / 24 VLANs only. 8 tenants empty. 180 IPs and 180 VMs have no tenant | "IPs per tenant across sites" impossible |
| Change history | **0 ObjectChange rows**; demo `created` dates 2020-12 → 2022-01 (preserved by SQL) | all "what changed" questions impossible |

**Operational findings (found incidentally, all affect enrichment):**

- **Job queue down.** Container `netbox-docker-redis-1` (Valkey 8.1.2) exited: *"Bad file format reading
  the append only file appendonly.aof.47.incr.aof"* (volume `netbox-docker_netbox-redis-data`).
  - `netbox-worker` then fails: *"Error -3 connecting to redis:6379"*.
  - Net effect: `/api/status/` returns **HTTP 500**, and background jobs and Custom Scripts can't run.
  - The REST API and GraphQL still work (they use `redis-cache`, which is healthy).
  - **✅ Resolved 2026-09-16.** `valkey-check-aof --fix` truncated **235 corrupt bytes** from the tail of the
    21 MB `appendonly.aof.47.incr.aof` (`ok_up_to=21017974`) → *"All AOF files and manifest are valid"*. The
    original directory is backed up in-volume as `appendonlydir.bak-20260916`. `redis` and `netbox-worker`
    both restarted **healthy** with `restarts=0`; the AOF now loads cleanly; the worker drained its stale
    backlog (jobs completing OK); `/api/status/` returns **200** with `rq-workers-running: 1`.
- **Change-log retention.** `CHANGELOG_RETENTION` is unset, so NetBox's **90-day default** applies, and the
  `netbox-housekeeping` container (running) prunes daily.
- **Tokens.** Both API tokens are `write_enabled=True`. The agent's token can list every token, so it
  belongs to a **superuser**.
  - Read-only is enforced only at the tool layer (MCP read-only tools + the GraphQL AST check), not at the
    credential. **✅ Resolved 2026-09-16** — the agent now uses a dedicated non-superuser `llm-agent` token
    with `write_enabled=false` and view-only permissions (see §9.4).
  - Separately, the demo dump contains **no `users_token` rows**, so reloading the demo **wipes the agent's
    token**.

## 2. Archetype sufficiency — what v5 can test on today's data

Verdicts:
- ✅ **answerable**: meaningful, non-degenerate answer exists
- ◑ **degenerate**: answerable, but the answer is uniform ("all", "none", "0%") so it tests nothing
- ❌ **impossible**: the data does not exist

| # | Archetype (from the v5 design) | Tier | Today | Blocking gap |
|---|---|---|---|---|
| 1 | Serial + asset tag of a device | S | ❌ | 0 serials / asset tags |
| 2 | Which device/interface holds IP X | S | ❌ | 0 IP assignments |
| 3 | Rack + position of a device | S | ✅ | — |
| 4 | Description + status of a prefix | S | ◑ | statuses uniform (active/container) |
| 5 | Provider + CID of a circuit | S | ✅ | — |
| 6 | Active devices at a site | M | ◑ | 100% active (filter does nothing) |
| 7 | Interface count / enabled on a device | M | ✅ | (enabled variety unverified) |
| 8 | VLANs defined at a site | M | ✅ | — (DM, JBB) |
| 9 | IPs in a prefix, with DNS names | M | ❌ | site prefixes empty; no dns_name |
| 10 | VM count + status in a cluster | M | ◑ | all active; no resources |
| 11 | Devices of type X across sites | M | ✅ | — |
| 12 | What changed on X in a date window | M | ❌ | 0 change-log rows |
| 13 | Active devices with no primary IP (audit) | A | ◑ | answer = all 72 |
| 14 | IP utilization % of a prefix | A | ◑ | 0% for every site prefix |
| 15 | Free rack units per rack | A | ✅ | limited variety |
| 16 | Next available IP / prefix | A | ◑ | trivially the first address |
| 17 | Cable trace to far-end device/port | A | ◑/✅ | circuit traces only; no multi-hop device↔device via patch panels; no broken path to find |
| 18 | All IPs for a tenant across sites | A | ❌ | 0 tenant IPs |
| 19 | Circuits per provider + termination sites | A | ✅ | — |
| 20 | Device counts per site by role | A | ✅ | — |
| 21 | Interfaces with no IP at a site (audit) | A | ◑ | answer = all |
| 22 | Devices/interfaces on VLAN N | A | ❌ | 0 VLAN assignments |

**Score:**

| Tier | ✅ Answerable | ◑ Degenerate | ❌ Impossible |
|---|---|---|---|
| SIMPLE (5) | 2 | 1 | 2 |
| MEDIUM (7) | 3 | 2 | 2 |
| **ADVANCED (10)** | **3** (15, 19, 20) | 5 | 2 |

The routing-relevant conclusion: **the tier model-handoff routing most needs to test — ADVANCED — is the
tier the current data cannot support.** Negative-finding, capacity-math and audit questions are exactly
where cheap models fail, and on today's data their "correct" answers are uniform and trivially guessable.

## 3. What must be enriched (prioritized gap list)

| Priority | Enrichment | Unblocks archetypes |
|---|---|---|
| **P0** | IPs **assigned to interfaces** in **site-scoped prefixes**, with `dns_name`; **primary IPs** on most (not all) devices and VMs | 2, 9, 13, 14, 16, 18, 21 |
| **P0** | **Prefix utilization spread**: empty, partial, near-full, full (/31s, `mark_utilized` DHCP range), plus container prefixes with children | 14, 16 |
| **P0** | **Deliberate, documented defects** (missing primary IP, IP with no parent prefix, broken path, unracked device, …) with an answer key | 13, 21, audits |
| **P0** | **Change history** created through the API, with retention fixed | 12 |
| **P1** | **Interface VLAN assignments** (access untagged, uplinks tagged) and site-scoped VLAN groups | 22, 8 |
| **P1** | **Multi-hop cable paths**: interface → patch panel front → rear → trunk → rear → front → interface, plus one broken path and one planned cable | 17 |
| **P1** | **Lifecycle status variety** (planned / offline / decommissioning / staged) on devices, VMs, circuits, sites, prefixes | 6, 10, 4 |
| **P1** | **VM resources** (vCPU, memory MB, virtual disks), cluster scope to site, host pinning, VM primary IPs | 10 |
| **P2** | **Power chain continuity**: panel → cabled feed → PDU power port → outlets → dual-fed device power supplies with allocated draw | power questions |
| **P2** | Serial numbers / asset tags (including one duplicate pair); circuit commit rates, install and termination dates; provider accounts | 1, circuit questions |
| **P3** | Services, contacts per site, a few journal entries; optionally wireless LANs/links, FHRP groups | stretch archetypes |

## 4. Strategy — additive tenant, pinned snapshots, v4 kept valid

**Enrich additively, don't mutate the demo objects.** 5 of the 6 v4 reference answers assert facts about
existing Dunder-Mifflin/NC State objects that enrichment would falsify: "0 IPs" on `dmi01-nashua-rtr01`,
"0%" utilization at DM sites, "no devices/IPs" on VLAN 100, "no power" at Butler. Modelling a **new tenant in
unused address space** leaves them true. It also gives a clean seam:
- **SIMPLE/MEDIUM** questions can keep using the familiar demo objects.
- **ADVANCED** questions target the fully-modelled new tenant.
- The **mixed-tenant** set is itself good routing data.

**Two pinned snapshots, one instance:**
- `00-demo-v4.3.dump`: taken **before** any write. The ground truth for v4.
- `bench-v5-1.dump`: taken after enrichment. The ground truth for v5.
- Store the sha256 of each. Restore with `pg_restore --clean --if-exists`.
- **The benchmark is pinned to the dump, not to re-running the seed.** Seeding is serial and
  deterministic, but a pinned artefact removes all doubt.

**Collision rules, so v4 also stays valid on the enriched snapshot:**
- **Don't reuse VLAN VID 100.** v4 Q3 asserts "VLAN 100 exists only within Dunder-Mifflin"; v4 Q3b asserts
  "deployed at 13 sites". Use e.g. 110/210/310 for the new tenant.
- **Avoid the demo address space.** Demo uses 10.112.0.0/15, 172.16–20.0.0/16, 192.168.0.0/20. Proposed:
  **10.60.0.0/16**.
- **Patch one v4 sentence.** The v4 site-comparison reference contains a *global* claim ("every one of the
  180 IP addresses in NetBox…"). That becomes false once IPs are added. The DM-specific fact (0%
  utilization) stays true. Either rephrase that one sentence in a v4 revision, or run v4 only against
  `00-demo-v4.3.dump`.
- **Scope global audits to the tenant.** Globally, "devices without a primary IP" includes all 72 demo
  devices. Scope audit questions to the tenant/region, or keep one global variant *on purpose* as a hard
  question.

## 5. Enrichment blueprint (summary)

A single fictional tenant sized for a one-person lab (hundreds, not thousands, of objects). The full
blueprint, with per-object detail, came from the dataset-shape research.

| Area | Target |
|---|---|
| Organisation | Tenant **Halvorsen Logistics** (`hvl`) in tenant group "Enterprise"; region "Pacific Northwest"; 3 site groups; **6 sites** (DC1, HQ, BR01–BR03 active, BR04 **planned**); 8 locations; ~4 contacts / ~8 assignments; users `hvl-seed`, `jdoe`, `facilities` (so the change log shows different actors) |
| Racks | **10 racks** with deliberate fill spread: 0% · ~26% · ~31% · **~88%** (includes a 20 U reservation) · branch 33–42%; 2 reservations |
| Devices | **~74**; ~16 new device types with full component templates; new roles Firewall, Console Server, Management Switch, Hypervisor Host, Storage, Wireless AP; naming `sea-dc1-core01` |
| IPAM | VRF **HVL-CORP** (10.60.0.0/16, `enforce_unique`); site containers (/20 DC and HQ, /22 branches); role /24s and /28 management; 12 × /31 point-to-point; 14 × /32 loopbacks; utilization spread **0% · ~9% · ~53% · ~80% (DHCP `mark_utilized`) · 93% · 100%**; VRF **HVL-GUEST** (`enforce_unique` off) with 4 identical 192.168.100.0/24 (intended duplicates); ~62 prefixes; **~200 IPs** with roles (Loopback / VRRP / VIP …); **58 of 62 eligible devices** get a primary IP |
| VLANs | 6 site-scoped VLAN groups, ~31 VLANs; access ports untagged, uplinks tagged |
| Cabling | **~250 cables** (~26% of interfaces); **8 multi-hop patch-panel trunk paths** DC and HQ; user patches ending at a rear port by design; console, management and power cables |
| Power | 3 panels; 11 feeds (DC 208V/30A A+B per rack, HQ 120V/20A; R04 feeds planned and uncabled); 12 PDUs; dual-fed supplies with allocated draw, so rack power ranges from ~20% to ~50% |
| Circuits | **4 providers**, **14 circuits**, 21 terminations; Evergreen 7 / Cascadia 3 / Rainier 3 / Summit 1; speeds 50 Mbps – 10 Gbps; one *provisioning* (BR04), one *decommissioned but still terminated* |
| Virtualization | 2 cluster groups; **3 site-scoped clusters** (PROD 24 VMs, MGMT 6 VMs, one planned/empty KVM); **30 VMs** with vCPU/memory(MB) and ~40 virtual disks; statuses 26 active / 2 offline / 1 planned / 1 decommissioning; host pinning; 27/30 with primary IP; platforms Ubuntu 22.04 / Windows Server 2022 / RHEL 9 |
| **Defects (answer key)** | **17 planted, written to `defects.yaml`**, each with its expected answer. D1 active devices without primary IP (3) · D2 IPs without parent prefix (2) · D3 IP mask ≠ subnet (1) · D4 nested active prefix (1) · D5 duplicate prefixes in the GUEST VRF (4) · D6 broken multi-hop path (1) · D7 planned/half-terminated cable · D8 unracked / unpositioned device · D9 console gap · D10 single power supply connected · D11 VLAN with no prefix and no interfaces (2) · D12 non-active lifecycles · D13 naming violation · D14 device without tenant (2) · D15 duplicate serial pair · D16 empty cluster / host with no VMs / VM IP not primary · D17 stale decommissioned circuit |
| **Legit-by-design traps** | Patch panels with no IP, APs with no rack, internet circuits with no Z side, branch PDUs with no feed, guest duplicates, user paths ending at a rear port. The agent should *not* flag these; they are good negative-finding tests |

Net effect: roughly **doubles** the instance, and turns every ◑/❌ archetype in §2 into a non-degenerate,
gradable question.

### 5.1 Does the additive tenant satisfy v5? (assessed 2026-09-16)

**Verdict: it satisfies v5's coverage and volume requirements — conditionally.** Three of the four
conditions below are question-design rules; the first is a genuine validity threat to the routing
benchmark and must be designed for deliberately.

**Coverage — yes.** Every ◑/❌ archetype in §2 is closed by the blueprint (mapping in §3). All 22 become
answerable with non-degenerate answers.

**Volume — yes, comfortably.** v5 targets 30–50 examples per tier:

| Tier | Available material | Verdict |
|---|---|---|
| ADVANCED (needs 30–50) | ~45–60 distinct candidates: ~62 prefixes with varied utilization · 10 racks · 8 traceable multi-hop paths + 1 broken · **17 defect classes** · 4 providers · 11 power feeds · 3 clusters · 6 sites · ~80–120 change-log events | ✅ |
| MEDIUM | filtered lists / counts across HVL **and** the demo tenants (DM 14 sites, JBB 6, NCSU 4) | ✅ ample |
| SIMPLE | ~146 devices total, ~62 new prefixes, 14 new circuits, 30 VMs | ✅ ample |

**Condition 1 — cross the tiers over BOTH data islands (the validity threat).**
If every ADVANCED question targets Halvorsen and every SIMPLE one targets the demo data, **the tenant name
becomes a proxy for difficulty**. A model could then appear to route correctly by keying on "HVL" rather
than on query shape — measuring the wrong thing, and precisely the miscalibration the anchor-object routing
fix corrected. **Required:** include SIMPLE questions about HVL objects, and keep MEDIUM/ADVANCED questions
on demo data (circuits per provider, rack fill, device counts per site and per role all work on the demo
data today). Difficulty must correlate with *query shape*, never with *which tenant is named*.

**Condition 2 — cap near-duplicates.** "Utilization of prefix X" asked five times with different nouns adds
`n` without adding information, and the confidence-interval maths in the v5 design assumes reasonably
independent items. Cap each archetype at ~3–5 instances and vary the *shape*, not just the object.

**Condition 3 — include the P3 items for full domain coverage.** Services, journal entries, wireless
LANs/links and VPN tunnels are "stretch" in the blueprint. Omit them and those domains stay at zero, so a
claim of covering "what a NetOps team asks" would be overstated. FHRP groups, inventory items and config
contexts would also remain empty.

**Condition 4 — scope audit questions to the tenant.** Globally, "active devices with no primary IP" returns
the 72 demo devices plus the 3 planted ones. Scope audits to HVL, or keep one global variant deliberately as
a hard question with the demo background acknowledged in the answer key.

**Residual limitation (approach-independent):** change-history realism. The API cannot backdate timestamps
(§7), so all seeded history lands at seed time. Questions must use absolute windows or ordering rather than
"in the last 7 days", unless falsified timestamps are accepted (§9.3).

## 6. Toolchain and procedure

**Tool choice.** Chosen: **pynetbox 7.5.0** (the pinned match for NetBox 4.3) against the **REST API**, in an
idempotent Python seed script kept in git. Why:
- It is the only reproducible path that **also populates the change log**. ObjectChange rows are written
  only when a request context exists: API writes and *committed* Custom Scripts do; `nbshell`, raw ORM,
  SQL loads and netbox-initializers do not.
- Bulk `create([...])` per dependency layer; get-or-create by natural key; serial requests; fixed
  `random`/`Faker` seeds; every object tagged `bench-seed-v1`.

Alternatives considered:

| Option | Verdict |
|---|---|
| Custom Script (`runscript --commit`) | Equally valid if one atomic transaction is wanted, but needs the worker (currently down) |
| Ansible `netbox.netbox` 3.22.0 | The declarative option |
| netbox-initializers 4.3.x | Skipped: needs an image rebuild and writes **no change log** |
| Diode | Skipped: asynchronous reconciliation, extra services, and 4.3 needs an old plugin 1.2.0 |
| UI bulk import | Skipped: not scriptable |

**Dependency order:**
1. RIR, VRF, tenant and tags
2. manufacturer, device type (with templates), role, platform
3. site, location, rack
4. device (components auto-created from templates)
5. MAC address
6. IP assigned to an interface
7. `PATCH primary_ip4` (the IP must be on that device)
8. cables (`a_terminations` / `b_terminations`)
9. circuits → terminations → cables
10. power panel → feed → PDU cable → outlet → device cables
11. cluster → VM → VM interface → VM IP → VM primary IP
12. virtual disks, services, contacts, journal entries

Device types come from `netbox-community/devicetype-library` via `Device-Type-Library-Import`, with
`REPO_BRANCH` **pinned to a commit** and a limited `--vendors` list. The importer's last commit was
2025-03-11, so test it against 4.3 first.

**Procedure:**
1. **Prerequisites:**
   - repair the queue Valkey AOF (`valkey-check-aof --fix`) and restart `redis` + `netbox-worker`
   - set `CHANGELOG_RETENTION=0` and `JOB_RETENTION=0` in `/home/ola/netbox-docker/env/netbox.env`, and
     confirm no ConfigRevision overrides them
2. **Baseline:** `pg_dump -Fc` → `00-demo-v4.3.dump` + sha256.
3. **Tokens:**
   - create user `seeder` with a write token (short expiry)
   - create user `llm-agent` as a non-superuser whose group has a **view-only ObjectPermission**, with a
     token set to `write_enabled=false`
   - point the agent's `.env` at the read-only token
4. **Device types** (importer, pinned).
5. **Seed** the organisation → IPAM → devices → cabling → power → circuits → virtualization layers, and
   plant the defects.
6. **Activity phase:** ~80–120 API *updates and deletes* as `jdoe` / `facilities`, so the change log has
   real history, with some objects changed 2–3×. Options for when those changes land are in §9.
7. **Finalize:** `manage.py trace_paths --no-input` and `manage.py reindex` (safety nets; both are
   automatic for API writes), then `pg_dump -Fc` → `bench-v5-1.dump` + sha256.
8. **Gold answers:** a script using the **read-only token** computes every expected answer via REST or
   GraphQL (chaining calls, since MCP forbids multi-hop filters). Store the JSON next to the dump.
   **Never** use the blueprint's hand targets as the answer key.
9. **Reset:**
   - stop netbox, worker and housekeeping
   - `pg_restore --clean --if-exists --no-owner --role=netbox`
   - flush `redis-cache`
   - start the services
   - re-verify gold answers after every restore

## 7. NetBox 4.3 gotchas to design around

- **No backdating via the API.** `ObjectChange.time`, `created` and `last_updated` are set automatically and
  not editable. Timestamps are the seed time. Anchor change questions to **absolute** windows, and freeze
  the snapshot.
- **Change-log rows are ~87% component noise (measured 2026-09-16).** After seeding 70 devices, the log held
  2,319 rows: **1,113 `dcim.interface`**, 432 `frontport`, 291 `rearport`, 96 `poweroutlet`, 81 `powerport`
  — all auto-generated from device-type templates — against only 70 `dcim.device`, 42 `ipam.prefix` and
  31 `ipam.vlan`. Every row was `create`.
  - Consequence: *"how many changes were made?"* is answered by template noise, not by meaningful edits.
    Change-history questions **must filter by `changed_object_type`**, and the activity phase must generate
    **update/delete** actions so real edits are distinguishable from this bulk-create floor.
  - Backdating is only possible with `nbshell` `queryset.update(time=…)`. That is *falsified* audit data:
    lab-only, and documented if used.
- **Features not in 4.3.** `changelog_message` arrived in **4.4**, and VirtualMachineType in **4.6**. Don't
  design questions or seed steps around them; use the tag + dedicated seeder user + `X-Request-ID` to
  label seed changes instead. (One research thread recommended `changelog_message`; the 4.4 release notes
  show it does not exist in 4.3.)
- **Container utilization counts only same-VRF children.** A global container over VRF children reports 0%.
  Put containers in the same VRF as their children.
- **Utilization quirks.** /31 and /32 count all addresses. `mark_utilized` means 100%. Utilization is
  computed live (never stored), so it is always consistent with the IPs present.
- **`children` is the child-PREFIX count, NOT the address count** (verified 2026-09-16 across five
  prefixes: `172.16.0.0/24` reports `children=0` while holding 30 IPs; `10.112.0.0/15` reports
  `children=67` while holding 0). **No utilization percentage is exposed on the prefix serializer at all.**
  - Gold-answer rule: **utilization % = (`?parent=<prefix>` IP count) ÷ usable addresses**, where usable =
    `num_addresses - 2` for IPv4 prefixes shorter than /31, and all addresses for /31 and /32.
  - Using `children` for utilization would make every such answer wrong.
- **`mark_utilized` IS writable** (present and not read-only in POST *and* PUT metadata; an empirical PATCH
  `False -> True` stuck and was reverted). It forces 100% regardless of child IPs, so it models a
  "DHCP pool fully allocated" prefix whose utilization is *not* derivable by counting addresses -- a
  deliberately different utilization rule for the benchmark to test.
- **Rack utilization.** Counts reservations as occupied, excludes 0 U devices, and skips device types with
  `exclude_from_utilization`. Decide explicitly whether patch panels and PDUs count, and record it in the
  answer key.
- **Global uniqueness.** `ENFORCE_GLOBAL_UNIQUE` defaults to true, so duplicate prefixes are only possible in
  a VRF with `enforce_unique=false` (hence the GUEST VRF).
- **Cable paths** are computed synchronously on cable save. A rear port with no cable ends a trace (correct
  for user patches).
- **Deleting a device leaves its cables half-terminated** (verified 2026-09-16). Removing
  `por-br02-ap01` deleted the device, its interface, its IP and 13 `CableTermination` rows — but the
  `Cable` objects themselves survived. Cable 188 remains `status=connected` with an **empty A side**, so
  `por-br02-sw01:Gi1/0/24` still reports as cabled to a cable that connects nothing.
  - Consequence for the benchmark: "what is connected to this port?" has a misleading answer, which is a
    genuinely good trap — but it is **emergent, not planted**, so it must be in the answer key or an agent
    that correctly reports it gets marked wrong. Adopted as **D18**.
  - This is the community `find_orphaned_cables` audit class. Any seeder that deletes devices should scan
    for `a_terminations == [] or b_terminations == []` afterwards.
- **Orphan cables.** D7's "half-terminated cable" may not be creatable: deleting one termination may delete
  the cable. Verify at build time and drop that defect if so.
- **Change-log noise.** Components auto-created from device-type templates may generate change-log rows
  (unverified). Phrase history questions per object type.
- **Reloading the demo SQL wipes users and tokens.** Token creation belongs in the bootstrap step.

## 8. Effort and risk

| Work item | Estimate |
|---|---|
| Prerequisites (Valkey fix, retention, baseline snapshot, tokens) | ~1–2 h |
| Seed script (~800–1,200 lines Python, layered, idempotent) | 1–2 focused sessions, mostly agent-authored, then iterated against the instance |
| Activity phase + defects answer key | ~½ session (plus real elapsed time if spreading changes over days) |
| Gold-answer script + verification | ~½–1 session |
| Seed run time | minutes (hundreds of objects, serial REST) |

**Risks and mitigations:**

| Risk | Mitigation |
|---|---|
| Accidental damage to the demo data | Baseline snapshot first; additive design; `pg_restore` in minutes |
| v4 invalidation | Collision rules in §4; v4 can always run against `00-demo-v4.3.dump` |
| Answer-key drift | Gold answers computed from the snapshot, re-verified after restore |
| Device-Type-Library importer incompatible with 4.3 | Fall back to defining the ~16 device types directly in the seed |

## 9. Decisions needed before building

1. **Writing to NetBox.** Enrichment is an out-of-band *admin* seeding step, done with a separate write token.
   The agent and its tools stay strictly read-only. Confirm this is consistent with your READ-only
   requirement, which has applied to the agent's capabilities.
2. **Additive new tenant** (recommended, keeps v4 valid) **vs. enriching the existing demo tenants**
   (familiar names, but breaks 5/6 v4 references and needs v4 pinned to the baseline snapshot).
3. **Change-history realism:**
   - (a) spread real API changes over ~1–2 weeks of elapsed time (authentic, slow), or
   - (b) do all activity in one sitting and phrase questions by absolute window/order (fast, recommended),
     or
   - (c) backdate via `nbshell` (fast, but falsified timestamps).
4. ~~**Fix the agent token now**~~ — ✅ **DONE (2026-09-16).** Created a non-superuser `llm-agent` user, an
   ObjectPermission granting **`view` on all 156 object types**, and a token with **`write_enabled=false`**;
   `.env` now points at it. Verified: REST read 200 (72 devices), GraphQL tool read + schema introspection OK,
   MCP connects (4 tools) and `netbox_get_objects` returns data, and `POST /api/dcim/sites/` → **HTTP 403**.
   The two pre-existing superuser tokens were left untouched as the rollback path. Read-only is now enforced
   at the **credential** as well as the tool layer.
   - *Residual:* the permission covers all object types, so the agent can still *view* `users.token`
     (keys are masked). Tightening it to exclude `users.*` is an optional next step.
5. ~~**Repairing the queue Valkey AOF**~~ — ✅ **DONE (2026-09-16).** Backed up `appendonlydir` in-volume,
   ran `valkey-check-aof --fix` (truncated 235 corrupt trailing bytes), restarted `redis` + `netbox-worker`.
   Both **healthy**, `restarts=0`, worker processing jobs, `/api/status/` **200** with one RQ worker running.
   Background jobs and Custom Scripts are available again — which also makes the Custom Script seeding option
   (§6) viable, not just the REST path.

## Sources

- **Live audit:** read-only REST GET audit scripts (session scratchpad). netbox-docker container
  logs/labels; demo-data repo `README.md` + `git log`.
- **Demo data:**
  - https://github.com/netbox-community/netbox-demo-data
  - https://github.com/netbox-community/netbox-docker/wiki/Troubleshooting
  - netbox-docker `docker-entrypoint.sh`
- **NetBox docs and v4.3 source:**
  - REST API bulk operations
  - change logging (`core/signals.py`, `core/models/change_logging.py`)
  - `dcim/signals.py` / `models/cables.py` (cable paths)
  - `ipam/models/ip.py` (utilization)
  - `dcim/models/racks.py`
  - models for prefix, IP address, VLAN group, device, power feed, power port, circuit, circuit
    termination, virtual machine, cluster
  - `configuration/miscellaneous.md` (`ENFORCE_GLOBAL_UNIQUE`)
  - release notes 4.4 / 4.6
- **Tooling:**
  - pynetbox (PyPI, compatibility table)
  - netbox-initializers (tobiasge)
  - Diode + diode-netbox-plugin
  - `netbox-community/ansible_modules`
  - devicetype-library + Device-Type-Library-Import
  - netbox-zero-to-hero
- **Dataset shape:**
  - NetBox Labs *Zero to Hero* modules 2–5, 8–10, 12
  - https://netboxlabs.com/blog/getting-started-with-netbox-reports/
  - `netbox-community/customizations` (ip-check-prefix, ip-duplicate, DeviceRackingReport,
    CheckConsoleOOBPower, CheckCableLocality, find_orphaned_cables, circuit_audits)
  - Uptime Institute Global Data Center Survey 2024 (rack density)
