"""The Halvorsen Logistics (HVL) blueprint -- data, not behaviour.

Sizing targets come from the enrichment research; every VALUE here is chosen so
that some v5 benchmark question has a meaningful, non-degenerate answer.

Two rules govern everything below:
  1. ADDITIVE -- nothing here touches a demo object, so the v4 reference
     answers stay true. VID 100 is forbidden; address space is 10.60.0.0/16.
  2. DELIBERATE GAPS -- the defects in DEFECTS are planted on purpose and are
     the answer key for the audit/negative-finding questions. Some *other*
     gaps are legitimate-by-design traps the agent should NOT flag.
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Sites -- one DC, one HQ, four branches (one deliberately `planned`)
# --------------------------------------------------------------------------
SITES = [
    {"name": "HVL-SEA-DC1", "slug": "hvl-sea-dc1", "status": "active",
     "group": "hvl-data-centers", "locations": ["Data Hall 1", "Meet-Me Room"]},
    {"name": "HVL-SEA-HQ", "slug": "hvl-sea-hq", "status": "active",
     "group": "hvl-campus", "locations": ["MDF", "IDF-2"]},
    {"name": "HVL-TAC-BR01", "slug": "hvl-tac-br01", "status": "active",
     "group": "hvl-branches", "locations": ["Comms Room"]},
    {"name": "HVL-POR-BR02", "slug": "hvl-por-br02", "status": "active",
     "group": "hvl-branches", "locations": ["Comms Room"]},
    {"name": "HVL-SPO-BR03", "slug": "hvl-spo-br03", "status": "active",
     "group": "hvl-branches", "locations": ["Comms Room"]},
    # planned site -> "which sites are not yet live?" has an answer
    {"name": "HVL-BOI-BR04", "slug": "hvl-boi-br04", "status": "planned",
     "group": "hvl-branches", "locations": ["Comms Room"]},
]

SITE_GROUPS = [
    {"name": "HVL Data Centers", "slug": "hvl-data-centers"},
    {"name": "HVL Campus", "slug": "hvl-campus"},
    {"name": "HVL Branches", "slug": "hvl-branches"},
]

# --------------------------------------------------------------------------
# Racks -- fill spread is deliberate: 0% / ~26% / ~31% / ~88%
# (free-rack-units questions need variety, not uniformity)
# --------------------------------------------------------------------------
RACKS = [
    {"name": "DC1-R01", "site": "hvl-sea-dc1", "location": "Data Hall 1",
     "u_height": 42, "status": "active"},
    {"name": "DC1-R02", "site": "hvl-sea-dc1", "location": "Data Hall 1",
     "u_height": 42, "status": "active"},          # ~88% + 20U reservation
    {"name": "DC1-R03", "site": "hvl-sea-dc1", "location": "Data Hall 1",
     "u_height": 42, "status": "active"},
    {"name": "DC1-R04", "site": "hvl-sea-dc1", "location": "Data Hall 1",
     "u_height": 42, "status": "available"},       # empty on purpose -> 0%
    {"name": "HQ-MDF-R01", "site": "hvl-sea-hq", "location": "MDF",
     "u_height": 42, "status": "active"},
    {"name": "HQ-IDF2-R01", "site": "hvl-sea-hq", "location": "IDF-2",
     "u_height": 12, "status": "active"},
    {"name": "BR01-R01", "site": "hvl-tac-br01", "location": "Comms Room",
     "u_height": 12, "status": "active"},
    {"name": "BR02-R01", "site": "hvl-por-br02", "location": "Comms Room",
     "u_height": 12, "status": "active"},
    {"name": "BR03-R01", "site": "hvl-spo-br03", "location": "Comms Room",
     "u_height": 12, "status": "active"},
    {"name": "BR04-R01", "site": "hvl-boi-br04", "location": "Comms Room",
     "u_height": 12, "status": "planned"},
]

# units are counted from the top; description is REQUIRED by the API
RACK_RESERVATIONS = [
    {"rack": "DC1-R02", "units": list(range(20, 40)),
     "description": "GPU expansion (Q1) - do not allocate"},
    # kept low in the rack: U39-42 hold pp03 and the leaf pair
    {"rack": "DC1-R03", "units": [20, 21, 22, 23],
     "description": "Spare capacity for storage growth"},
]

# --------------------------------------------------------------------------
# Devices -- role, type key (see config.REUSE_DEVICE_TYPES / NEW_DEVICE_TYPES),
# rack position, status. `tenant: False` marks a deliberate defect (D14).
# --------------------------------------------------------------------------
DEVICES = [
    # ---- DC1: network core ------------------------------------------------
    {"name": "sea-dc1-core01", "type": "core", "role": "core-switch",
     "site": "hvl-sea-dc1", "rack": "DC1-R01", "position": 40},
    {"name": "sea-dc1-core02", "type": "core", "role": "core-switch",
     "site": "hvl-sea-dc1", "rack": "DC1-R01", "position": 38},
    {"name": "sea-dc1-fw01", "type": "pa-3220", "role": "firewall",
     "site": "hvl-sea-dc1", "rack": "DC1-R01", "position": 36},
    {"name": "sea-dc1-fw02", "type": "pa-3220", "role": "firewall",
     "site": "hvl-sea-dc1", "rack": "DC1-R01", "position": 34},
    {"name": "sea-dc1-rtr01", "type": "branch-router", "role": "router",
     "site": "hvl-sea-dc1", "rack": "DC1-R01", "position": 33},
    {"name": "sea-dc1-rtr02", "type": "branch-router", "role": "router",
     "site": "hvl-sea-dc1", "rack": "DC1-R01", "position": 32},
    {"name": "sea-dc1-oob-sw01", "type": "access-switch", "role": "management-switch",
     "site": "hvl-sea-dc1", "rack": "DC1-R01", "position": 31},
    {"name": "sea-dc1-con01", "type": "cm7116-2", "role": "console-server",
     "site": "hvl-sea-dc1", "rack": "DC1-R01", "position": 30},
    {"name": "sea-dc1-pp01", "type": "patch-panel-fiber", "role": "patch-panel",
     "site": "hvl-sea-dc1", "rack": "DC1-R01", "position": 28},
    # ---- DC1: compute A (high fill, ~88%) ---------------------------------
    {"name": "sea-dc1-leaf01", "type": "leaf", "role": "tor-switch",
     "site": "hvl-sea-dc1", "rack": "DC1-R02", "position": 42},
    {"name": "sea-dc1-leaf02", "type": "leaf", "role": "tor-switch",
     "site": "hvl-sea-dc1", "rack": "DC1-R02", "position": 41},
    # 2U -> occupies U18-19; must stay clear of the 20-39 reservation
    {"name": "sea-dc1-pp02", "type": "patch-panel-copper", "role": "patch-panel",
     "site": "hvl-sea-dc1", "rack": "DC1-R02", "position": 18},
    *[{"name": f"sea-dc1-esx{i:02d}", "type": "poweredge-r650",
       "role": "hypervisor-host", "site": "hvl-sea-dc1", "rack": "DC1-R02",
       "position": 18 - i, "platform": "ubuntu-22-04"} for i in range(1, 6)],
    # ---- DC1: compute B ---------------------------------------------------
    {"name": "sea-dc1-leaf03", "type": "leaf", "role": "tor-switch",
     "site": "hvl-sea-dc1", "rack": "DC1-R03", "position": 42},
    {"name": "sea-dc1-leaf04", "type": "leaf", "role": "tor-switch",
     "site": "hvl-sea-dc1", "rack": "DC1-R03", "position": 41},
    {"name": "sea-dc1-pp03", "type": "patch-panel-copper", "role": "patch-panel",
     "site": "hvl-sea-dc1", "rack": "DC1-R03", "position": 38},
    *[{"name": f"sea-dc1-esx{i:02d}", "type": "poweredge-r650",
       "role": "hypervisor-host", "site": "hvl-sea-dc1", "rack": "DC1-R03",
       "position": 36 - i, "platform": "ubuntu-22-04"} for i in range(6, 9)],
    # unracked but ACTIVE -> defect D8
    {"name": "sea-dc1-esx09", "type": "poweredge-r650", "role": "hypervisor-host",
     "site": "hvl-sea-dc1", "rack": None, "position": None,
     "platform": "ubuntu-22-04"},
    # ---- DC1 PDUs (0U, excluded from rack fill) ---------------------------
    *[{"name": f"sea-dc1-pdu{i:02d}", "type": "pdu", "role": "pdu",
       "site": "hvl-sea-dc1", "rack": r, "position": None}
      for i, r in [(1, "DC1-R01"), (2, "DC1-R01"), (3, "DC1-R02"),
                   (4, "DC1-R02"), (5, "DC1-R03"), (6, "DC1-R03")]],
    # ---- HQ ---------------------------------------------------------------
    {"name": "hq-rtr01", "type": "branch-router", "role": "router",
     "site": "hvl-sea-hq", "rack": "HQ-MDF-R01", "position": 42},
    {"name": "hq-fw01", "type": "pa-3220", "role": "firewall",
     "site": "hvl-sea-hq", "rack": "HQ-MDF-R01", "position": 40},
    {"name": "hq-dist01", "type": "leaf", "role": "distribution-switch",
     "site": "hvl-sea-hq", "rack": "HQ-MDF-R01", "position": 38},
    {"name": "hq-dist02", "type": "leaf", "role": "distribution-switch",
     "site": "hvl-sea-hq", "rack": "HQ-MDF-R01", "position": 37},
    {"name": "hq-acc01", "type": "access-switch", "role": "access-switch",
     "site": "hvl-sea-hq", "rack": "HQ-MDF-R01", "position": 35},
    # decommissioning but still cabled -> defect D12
    {"name": "hq-acc02", "type": "access-switch", "role": "access-switch",
     "site": "hvl-sea-hq", "rack": "HQ-MDF-R01", "position": 34,
     "status": "decommissioning"},
    {"name": "hq-pp01", "type": "patch-panel-fiber", "role": "patch-panel",
     "site": "hvl-sea-hq", "rack": "HQ-MDF-R01", "position": 32},
    {"name": "hq-pp02", "type": "patch-panel-copper", "role": "patch-panel",
     "site": "hvl-sea-hq", "rack": "HQ-MDF-R01", "position": 30},
    # racked but NO position -> defect D8
    {"name": "hq-con01", "type": "cm7116-2", "role": "console-server",
     "site": "hvl-sea-hq", "rack": "HQ-MDF-R01", "position": None},
    {"name": "hq-acc03", "type": "access-switch", "role": "access-switch",
     "site": "hvl-sea-hq", "rack": "HQ-IDF2-R01", "position": 12},
    # no primary IP will be set -> defect D1
    {"name": "hq-acc04", "type": "access-switch", "role": "access-switch",
     "site": "hvl-sea-hq", "rack": "HQ-IDF2-R01", "position": 11},
    {"name": "hq-pp03", "type": "patch-panel-fiber", "role": "patch-panel",
     "site": "hvl-sea-hq", "rack": "HQ-IDF2-R01", "position": 9},
    *[{"name": f"hq-pdu{i:02d}", "type": "pdu", "role": "pdu",
       "site": "hvl-sea-hq", "rack": r, "position": None}
      for i, r in [(1, "HQ-MDF-R01"), (2, "HQ-MDF-R01"), (3, "HQ-IDF2-R01")]],
    # APs: 0U, deliberately NOT racked (legitimate, should NOT be flagged)
    *[{"name": f"hq-ap{i:02d}", "type": "u6-pro", "role": "wireless-ap",
       "site": "hvl-sea-hq", "rack": None, "position": None} for i in range(1, 7)],
    # ---- Branches ---------------------------------------------------------
    *[d for site, pfx, rack in [
        ("hvl-tac-br01", "tac-br01", "BR01-R01"),
        ("hvl-por-br02", "por-br02", "BR02-R01"),
        ("hvl-spo-br03", "spo-br03", "BR03-R01"),
      ] for d in [
        {"name": f"{pfx}-rtr01", "type": "branch-router", "role": "router",
         "site": site, "rack": rack, "position": 12},
        {"name": f"{pfx}-sw01", "type": "access-switch", "role": "access-switch",
         "site": site, "rack": rack, "position": 10},
        {"name": f"{pfx}-pp01", "type": "patch-panel-copper", "role": "patch-panel",
         "site": site, "rack": rack, "position": 7},
        {"name": f"{pfx}-pdu01", "type": "pdu", "role": "pdu",
         "site": site, "rack": rack, "position": None},
      ]],
    # BR01 second switch; BR02/BR03 APs
    {"name": "tac-br01-sw02", "type": "access-switch", "role": "access-switch",
     "site": "hvl-tac-br01", "rack": "BR01-R01", "position": 9},
    # no tenant -> defect D14
    {"name": "tac-br01-ap01", "type": "u6-pro", "role": "wireless-ap",
     "site": "hvl-tac-br01", "rack": None, "position": None, "tenant": False},
    {"name": "por-br02-ap01", "type": "u6-pro", "role": "wireless-ap",
     "site": "hvl-por-br02", "rack": None, "position": None},
    # offline -> defect D12
    {"name": "spo-br03-ap02", "type": "u6-pro", "role": "wireless-ap",
     "site": "hvl-spo-br03", "rack": None, "position": None, "status": "offline"},
    # naming-convention violation -> defect D13
    # U9: pp01 is 2U at U7-8
    {"name": "SPO-BR03-Switch1", "type": "access-switch", "role": "access-switch",
     "site": "hvl-spo-br03", "rack": "BR03-R01", "position": 9},
    # ---- BR04 (planned site, planned devices) -----------------------------
    {"name": "boi-br04-rtr01", "type": "branch-router", "role": "router",
     "site": "hvl-boi-br04", "rack": "BR04-R01", "position": 12,
     "status": "planned"},
    {"name": "boi-br04-sw01", "type": "access-switch", "role": "access-switch",
     "site": "hvl-boi-br04", "rack": "BR04-R01", "position": 10,
     "status": "planned"},
]

# --------------------------------------------------------------------------
# VLANs -- VID 100 is FORBIDDEN (v4 collision). Branch/HQ use x10; DC uses 11xx.
# --------------------------------------------------------------------------
VLANS_BRANCH = [(110, "DATA"), (210, "VOICE"), (310, "WIFI"),
                (410, "GUEST"), (900, "MGMT")]
VLANS_DC = [(1110, "PROD"), (1120, "VMOTION"), (1130, "HYPERVISOR-MGMT"),
            (1140, "INFRA"), (900, "MGMT"),
            (999, "QUARANTINE")]   # no prefix, no interfaces -> defect D11

# --------------------------------------------------------------------------
# IPAM -- utilization spread is the point: 0% / ~9% / ~53% / ~80% / 93% / 100%
# --------------------------------------------------------------------------
VRF_CORP = {"name": "HVL-CORP", "rd": "65060:100", "enforce_unique": True}
VRF_GUEST = {"name": "HVL-GUEST", "rd": "65060:200", "enforce_unique": False}

PREFIX_PLAN = [
    # (prefix, status, role, scope_site, vlan_vid, fill_target, note)
    ("10.60.0.0/16", "container", None, None, None, 0, "HVL supernet"),
    ("10.60.0.0/20", "container", None, "hvl-sea-dc1", None, 0, "DC1 container"),
    ("10.60.1.0/24", "active", "management", "hvl-sea-dc1", 900, 23, "DC mgmt ~9%"),
    ("10.60.2.0/24", "active", "server", "hvl-sea-dc1", 1110, 25, "prod servers ~10%"),
    ("10.60.3.0/26", "active", "management", "hvl-sea-dc1", 1130, 8, "hypervisor mgmt ~13%"),
    ("10.60.4.0/24", "active", "server", "hvl-sea-dc1", 1120, 10, "vmotion"),
    ("10.60.16.0/20", "container", None, "hvl-sea-hq", None, 0, "HQ container"),
    ("10.60.17.0/24", "active", "access-data", "hvl-sea-hq", 110, 200, "HQ data ~80% (DHCP range)"),
    ("10.60.18.0/24", "active", "access-voice", "hvl-sea-hq", 210, 1, "HQ voice ~0.4%"),
    ("10.60.19.0/24", "active", "access-wireless", "hvl-sea-hq", 310, 12, "HQ wifi"),
    ("10.60.20.0/27", "active", "management", "hvl-sea-hq", 900, 16, "HQ mgmt ~53%"),
    ("10.60.32.0/22", "container", None, "hvl-tac-br01", None, 0, "BR01 container"),
    ("10.60.32.0/24", "active", "access-data", "hvl-tac-br01", 110, 20, "BR01 data"),
    ("10.60.33.0/28", "active", "management", "hvl-tac-br01", 900, 6, "BR01 mgmt"),
    ("10.60.36.0/22", "container", None, "hvl-por-br02", None, 0, "BR02 container"),
    ("10.60.36.0/24", "active", "access-data", "hvl-por-br02", 110, 18, "BR02 data"),
    ("10.60.37.0/28", "active", "management", "hvl-por-br02", 900, 13, "BR02 mgmt 93%"),
    ("10.60.40.0/22", "container", None, "hvl-spo-br03", None, 0, "BR03 container"),
    ("10.60.40.0/24", "active", "access-data", "hvl-spo-br03", 110, 15, "BR03 data"),
    ("10.60.41.0/28", "active", "management", "hvl-spo-br03", 900, 4, "BR03 mgmt"),
    # BR04 reserved -> 0%, "not yet in service"
    ("10.60.44.0/22", "container", None, "hvl-boi-br04", None, 0, "BR04 container"),
    ("10.60.44.0/24", "reserved", "access-data", "hvl-boi-br04", None, 0, "BR04 reserved"),
    ("10.60.253.0/24", "container", "point-to-point", None, None, 0, "WAN PE-CE"),
    ("10.60.254.0/24", "container", "point-to-point", None, None, 0, "P2P container"),
    ("10.60.255.0/24", "container", "loopback", None, None, 0, "loopbacks"),
]

# /31 point-to-point links -> 100% utilized each (no network/broadcast)
P2P_LINKS = [f"10.60.254.{i*2}/31" for i in range(12)]
# /32 loopbacks, role=loopback, become primary IPs for L3 devices
LOOPBACK_BASE = "10.60.255."

# --------------------------------------------------------------------------
# Circuits -- 4 providers, deliberately uneven so "per provider" discriminates
# --------------------------------------------------------------------------
PROVIDERS = [
    {"name": "Cascadia Fiber", "slug": "cascadia-fiber"},
    {"name": "Evergreen Networks", "slug": "evergreen-networks"},
    {"name": "Rainier Broadband", "slug": "rainier-broadband"},
    {"name": "Summit Wireless", "slug": "summit-wireless"},
]
NEW_CIRCUIT_TYPES = [
    {"name": "Broadband", "slug": "broadband"},
    {"name": "LTE", "slug": "lte"},
]
CIRCUITS = [
    # (cid, provider, type, site, status, commit_rate_kbps, cable_to)
    ("CF-DIA-1001", "cascadia-fiber", "internet", "hvl-sea-dc1", "active", 1000000, "sea-dc1-rtr01"),
    ("EV-MPLS-2001", "evergreen-networks", "mpls", "hvl-sea-dc1", "active", 500000, "sea-dc1-rtr02"),
    ("CF-METRO-1002", "cascadia-fiber", "dark-fiber", "hvl-sea-dc1", "active", 10000000, None),
    ("CF-DIA-1003", "cascadia-fiber", "internet", "hvl-sea-hq", "active", 500000, "hq-rtr01"),
    ("EV-MPLS-2002", "evergreen-networks", "mpls", "hvl-sea-hq", "active", 100000, None),
    ("EV-MPLS-2003", "evergreen-networks", "mpls", "hvl-tac-br01", "active", 50000, "tac-br01-rtr01"),
    ("EV-MPLS-2004", "evergreen-networks", "mpls", "hvl-por-br02", "active", 50000, "por-br02-rtr01"),
    ("EV-MPLS-2005", "evergreen-networks", "mpls", "hvl-spo-br03", "active", 50000, "spo-br03-rtr01"),
    ("RB-BB-3001", "rainier-broadband", "broadband", "hvl-tac-br01", "active", 300000, None),
    ("RB-BB-3002", "rainier-broadband", "broadband", "hvl-por-br02", "active", 300000, None),
    ("RB-BB-3003", "rainier-broadband", "broadband", "hvl-spo-br03", "active", 1000000, None),
    ("SW-LTE-4001", "summit-wireless", "lte", "hvl-spo-br03", "active", 50000, None),
    # provisioning, no cable -> BR04 not yet live
    ("EV-MPLS-2006", "evergreen-networks", "mpls", "hvl-boi-br04", "provisioning", None, None),
    # decommissioned but STILL terminated -> defect D17
    ("EV-MPLS-1999", "evergreen-networks", "mpls", "hvl-sea-hq", "decommissioned", 100000, None),
]

# --------------------------------------------------------------------------
# Power -- panel -> feed -> PDU -> device, with allocated draw so rack power
# math differs per rack (~20% vs ~50%)
# --------------------------------------------------------------------------
POWER_PANELS = [
    {"name": "DC1-PP-A", "site": "hvl-sea-dc1", "location": "Data Hall 1"},
    {"name": "DC1-PP-B", "site": "hvl-sea-dc1", "location": "Data Hall 1"},
    {"name": "HQ-MDF-PP1", "site": "hvl-sea-hq", "location": "MDF"},
]
POWER_FEEDS = [
    # (name, panel, rack, type, status, voltage, amperage)
    ("DC1-R01-A", "DC1-PP-A", "DC1-R01", "primary", "active", 208, 30),
    ("DC1-R01-B", "DC1-PP-B", "DC1-R01", "redundant", "active", 208, 30),
    ("DC1-R02-A", "DC1-PP-A", "DC1-R02", "primary", "active", 208, 30),
    ("DC1-R02-B", "DC1-PP-B", "DC1-R02", "redundant", "active", 208, 30),
    ("DC1-R03-A", "DC1-PP-A", "DC1-R03", "primary", "active", 208, 30),
    ("DC1-R03-B", "DC1-PP-B", "DC1-R03", "redundant", "active", 208, 30),
    # R04 planned + uncabled -> "which feeds are not yet in service?"
    ("DC1-R04-A", "DC1-PP-A", "DC1-R04", "primary", "planned", 208, 30),
    ("DC1-R04-B", "DC1-PP-B", "DC1-R04", "redundant", "planned", 208, 30),
    ("HQ-MDF-A", "HQ-MDF-PP1", "HQ-MDF-R01", "primary", "active", 120, 20),
    ("HQ-MDF-B", "HQ-MDF-PP1", "HQ-MDF-R01", "redundant", "active", 120, 20),
    ("HQ-IDF2-A", "HQ-MDF-PP1", "HQ-IDF2-R01", "primary", "active", 120, 20),
]

# --------------------------------------------------------------------------
# Virtualization
# --------------------------------------------------------------------------
CLUSTER_GROUPS = [
    {"name": "HVL Production", "slug": "hvl-production"},
    {"name": "HVL Management", "slug": "hvl-management"},
]
CLUSTERS = [
    {"name": "HVL-SEA-DC1-PROD", "type": "vmware", "group": "hvl-production",
     "site": "hvl-sea-dc1", "status": "active"},
    {"name": "HVL-SEA-DC1-MGMT", "type": "vmware", "group": "hvl-management",
     "site": "hvl-sea-dc1", "status": "active"},
    # planned, zero hosts and zero VMs -> defect D16
    {"name": "HVL-SEA-HQ-EDGE", "type": "kvm", "group": "hvl-management",
     "site": "hvl-sea-hq", "status": "planned"},
]
# (name, cluster, host_device, vcpus, memory_mb, disk_mb, status, platform)
VMS = (
    [(f"hvl-web{i:02d}", "HVL-SEA-DC1-PROD", f"sea-dc1-esx{((i-1)%4)+1:02d}",
      2, 4096, 51200, "active", "ubuntu-22-04") for i in range(1, 9)]
    + [(f"hvl-app{i:02d}", "HVL-SEA-DC1-PROD", f"sea-dc1-esx{((i-1)%4)+1:02d}",
        4, 8192, 102400, "active", "ubuntu-22-04") for i in range(1, 9)]
    + [(f"hvl-db{i:02d}", "HVL-SEA-DC1-PROD", f"sea-dc1-esx{((i-1)%2)+1:02d}",
        8, 32768, 204800, "active", "rhel-9") for i in range(1, 5)]
    + [("hvl-vcenter01", "HVL-SEA-DC1-MGMT", "sea-dc1-esx06", 4, 16384, 102400,
        "active", "ubuntu-22-04"),
       ("hvl-dns01", "HVL-SEA-DC1-MGMT", "sea-dc1-esx06", 2, 4096, 51200,
        "active", "ubuntu-22-04"),
       ("hvl-dns02", "HVL-SEA-DC1-MGMT", "sea-dc1-esx07", 2, 4096, 51200,
        "active", "ubuntu-22-04"),
       ("hvl-ntp01", "HVL-SEA-DC1-MGMT", "sea-dc1-esx07", 2, 4096, 51200,
        "offline", "ubuntu-22-04"),
       ("hvl-syslog01", "HVL-SEA-DC1-MGMT", "sea-dc1-esx08", 4, 8192, 512000,
        "active", "rhel-9"),
       ("hvl-backup01", "HVL-SEA-DC1-MGMT", None, 4, 8192, 1024000,
        "decommissioning", "windows-server-2022"),
       ("hvl-test01", "HVL-SEA-DC1-PROD", None, 2, 4096, 51200,
        "planned", "ubuntu-22-04"),
       ("hvl-fileshare01", "HVL-SEA-DC1-PROD", None, 4, 16384, 2048000,
        "offline", "windows-server-2022")]
)

# --------------------------------------------------------------------------
# DEFECTS -- the audit answer key. Written to defects.yaml at seed time.
# Expected counts are TARGETS; gold answers must be recomputed from the API.
# --------------------------------------------------------------------------
DEFECTS = {
    "D1": {"desc": "Active device with no primary IP",
           "objects": ["sea-dc1-leaf04", "hq-acc04", "por-br02-sw01"], "expect": 3},
    "D2": {"desc": "IP with no parent prefix",
           "objects": ["10.61.0.10/24 on sea-dc1-oob-sw01",
                       "10.60.50.1/24 on spo-br03-rtr01"], "expect": 2},
    "D3": {"desc": "IP mask does not match enclosing prefix",
           "objects": ["10.60.3.20/24 inside 10.60.3.0/26"], "expect": 1},
    "D4": {"desc": "Active prefix nested inside an active non-container prefix",
           "objects": ["10.60.36.128/25 under 10.60.36.0/24"], "expect": 1},
    "D5": {"desc": "Duplicate prefixes (intentional, GUEST VRF)",
           "objects": ["192.168.100.0/24 x4"], "expect": 4},
    "D6": {"desc": "Broken multi-hop cable path (ends at an uncabled front port)",
           "objects": ["hq-acc04 uplink via hq-pp03 -> hq-pp01 port 4"], "expect": 1},
    "D7": {"desc": "Planned cable between two active devices",
           "objects": ["hq-acc01 <-> hq-dist02 (status=planned)"], "expect": 1},
    "D8": {"desc": "Device unracked / racked without position",
           "objects": ["sea-dc1-esx09 (no rack)", "hq-con01 (no position)"],
           "expect": 2, "note": "APs are 0U and unracked BY DESIGN - not defects"},
    "D9": {"desc": "Console port not connected",
           "objects": ["sea-dc1-leaf03"], "expect": 1},
    "D10": {"desc": "Only one power supply connected",
            "objects": ["sea-dc1-esx05"], "expect": 1},
    "D11": {"desc": "VLAN with no prefix and no interfaces",
            "objects": ["DC1 VLAN 999 QUARANTINE", "BR03 VLAN 210 VOICE"], "expect": 2},
    "D12": {"desc": "Non-active lifecycle still in service",
            "objects": ["hq-acc02 (decommissioning, still cabled)",
                        "spo-br03-ap02 (offline)", "HVL-BOI-BR04 (planned site)"],
            "expect": 3},
    "D13": {"desc": "Naming-convention violation",
            "objects": ["SPO-BR03-Switch1"], "expect": 1},
    "D14": {"desc": "Device in HVL region with no tenant",
            "objects": ["tac-br01-ap01"], "expect": 1},
    "D15": {"desc": "Duplicate serial number",
            "objects": ["hq-acc01 and hq-acc03 share SN HVL-DUP-0001"], "expect": 1},
    "D16": {"desc": "Empty cluster / host with no VMs / VM with IP but not primary",
            "objects": ["HVL-SEA-HQ-EDGE (0 hosts, 0 VMs)",
                        "sea-dc1-esx05 (no VMs pinned)", "hvl-app08"], "expect": 3},
    "D17": {"desc": "Decommissioned circuit still terminated",
            "objects": ["EV-MPLS-1999"], "expect": 1},
}

# Gaps that are CORRECT and must NOT be reported as problems. These make good
# negative-finding questions in their own right.
LEGITIMATE_GAPS = [
    "Patch panels have no IP address (passive devices)",
    "Wireless APs are 0U and not racked (ceiling mounted)",
    "Internet circuits have only an A termination (no Z side)",
    "Branch PDUs have no power feed (no panel modelled at branches)",
    "192.168.100.0/24 duplicates are intentional (per-site guest, GUEST VRF)",
    "User patch paths end at a rear port (wall outlets are not modelled)",
]
