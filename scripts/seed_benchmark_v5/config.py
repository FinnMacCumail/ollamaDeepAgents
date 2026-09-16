"""Pinned constants for the netbox-benchmark-v5 enrichment seed.

Every value here was VERIFIED against the live instance (NetBox 4.3.3,
netbox-docker 3.3.0) on 2026-09-16 via read-only API discovery. Do not
"tidy" these from memory or from docs written for another NetBox version --
several differ from the published examples (see API NOTES below).

Design: ADDITIVE. We add one new tenant in unused address space and never
mutate the demo objects, so the netbox-benchmark-v4 reference answers stay
true. See docs/development/2026-09-15_netbox-v5-data-enrichment-research.md.
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------
# Connection
# --------------------------------------------------------------------------
SEED_TOKEN_PATH = Path("/home/ola/dev/netboxdev/.netbox-seed-token")


def netbox_url() -> str:
    url = os.environ.get("NETBOX_URL", "http://localhost:8000")
    return url.rstrip("/")


def seed_token() -> str:
    """Write-enabled seeder token. NEVER log this value."""
    tok = os.environ.get("NETBOX_SEED_TOKEN")
    if tok:
        return tok.strip()
    return SEED_TOKEN_PATH.read_text().strip()


# Marker applied to every object this seed creates, so seeded data is
# trivially separable from the demo background.
SEED_TAG = {"name": "bench-seed-v1", "slug": "bench-seed-v1", "color": "2196f3"}

# --------------------------------------------------------------------------
# API NOTES (verified via OPTIONS with the seeder token -- these bite)
# --------------------------------------------------------------------------
# * Prefix           -> scope_type + scope_id   (NOT `site`)
# * Cluster          -> scope_type + scope_id   (NOT `site`)
# * CircuitTermination -> termination_type + termination_id (NOT `site`)
# * Cable            -> a_terminations / b_terminations, each a list of
#                       {"object_type": "dcim.interface", "object_id": N}
# * IPAddress        -> assigned_object_type + assigned_object_id
# * Device           -> device_type, role, site are REQUIRED
# * VirtualMachine   -> has `device` (host pinning); memory/disk are INTEGER MB,
#                       vcpus is DECIMAL
# * VirtualDisk      -> virtual_machine + name + size (REQUIRED)
# * RackReservation  -> user AND description are REQUIRED
# * JournalEntry     -> assigned_object_type/_id + comments (REQUIRED)
# * A token's `key` is NEVER returned by the 4.3 API (absent from the
#   serializer, including on create) -- always POST an explicit key.
# * Component templates do NOT exist for every type. Where a device type has
#   no power-port template (e.g. C9200-48P), power ports must be created
#   EXPLICITLY per device -- this is what the demo data itself does.
# * Filter params are `device_type_id` / `devicetype_id` is silently IGNORED
#   (returns the unfiltered total). Always verify a filter narrows the count.

# --------------------------------------------------------------------------
# COLLISION RULES -- protect the netbox-benchmark-v4 reference answers
# --------------------------------------------------------------------------
# v4 asserts: "VLAN 100 ('Data') exists only within the Dunder-Mifflin tenant"
# and "deployed at 13 of 14 DM sites". So VID 100 is FORBIDDEN here.
FORBIDDEN_VIDS = {100}
# Demo occupies 10.112.0.0/15, 172.16-20.0.0/16, 192.168.0.0/20.
IPV4_SUPERNET = "10.60.0.0/16"          # clear of all demo space
PUBLIC_SUPERNET = "198.51.100.0/24"     # TEST-NET-2, documentation range
GUEST_DUP_PREFIX = "192.168.100.0/24"   # intentional duplicate, GUEST VRF only

# --------------------------------------------------------------------------
# EXISTING objects to REUSE (ids verified 2026-09-16)
# --------------------------------------------------------------------------
DEVICE_ROLES = {
    "router": 1, "core-switch": 2, "distribution-switch": 3,
    "access-switch": 4, "pdu": 5, "patch-panel": 6,
    "application-server": 7, "database-server": 8, "tor-switch": 9,
}
MANUFACTURERS = {
    "apc": 11, "arista": 1, "brocade": 2, "cisco": 3, "dell": 4, "extreme": 5,
    "f5": 6, "generic": 13, "juniper": 7, "lenovo": 14, "opengear": 8,
    "palo-alto": 9, "panduit": 12, "ubiquiti": 10,
}
CIRCUIT_TYPES = {"dark-fiber": 4, "internet": 1, "mpls": 2, "point-to-point": 3}
CLUSTER_TYPES = {"vmware": 5, "kvm": 6, "google-cloud": 2, "digitalocean": 4}
RIRS = {"rfc-1918": 6, "arin": 1}
PREFIX_ROLES_EXISTING = {
    "access-data": 1, "access-voice": 2, "access-wireless": 3,
    "management": 4, "testing": 5,
}
REGIONS_TOP = {"north-america": 1}
SITE_GROUPS_EXISTING = {"branch-offices": 2, "headquarters": 3}
TENANT_GROUP_EXISTING = {"customers": 1}

# Reusable device types -> real component-template names (verified).
# `power_ports` None means the type has NO power-port template and ports must
# be created explicitly on each device.
REUSE_DEVICE_TYPES = {
    "branch-router": {
        "id": 6, "model": "ISR 1111-8P", "u": 1,
        "uplink": "GigabitEthernet0/0/0", "wan2": "GigabitEthernet0/0/1",
        "lan": [f"GigabitEthernet0/1/{i}" for i in range(8)],
        "console": "con 0", "power_ports": ["PSU0"],
    },
    "access-switch": {
        "id": 7, "model": "C9200-48P", "u": 1,
        "mgmt": "GigabitEthernet0",
        "ports": [f"GigabitEthernet1/0/{i}" for i in range(1, 49)],
        "console": None, "power_ports": None,   # <- must create explicitly
    },
    "leaf": {
        "id": 12, "model": "QFX5110-48S-4C", "u": 1,
        "mgmt": "fxp0",
        "ports": [f"xe-0/0/{i}" for i in range(48)],
        "uplinks": [f"et-0/0/{i}" for i in range(48, 52)],
        "console": "Console", "power_ports": ["PSU0", "PSU1"],
    },
    "core": {
        "id": 13, "model": "QFX10002-36Q", "u": 2,
        "mgmt": "em0",
        "ports": [f"et-0/0/{i}" for i in range(36)],
        "console": "Console", "power_ports": ["PSU0", "PSU1"],
    },
    "pdu": {
        "id": 8, "model": "AP7901", "u": 1,
        "input": "Input", "outlets": [f"Outlet {i}" for i in range(1, 9)],
        "console": None, "power_ports": ["Input"],
    },
    "patch-panel-copper": {   # 48 front <-> 48 rear, 1:1
        "id": 10, "model": "48-Port Patch Panel", "u": 2,
        "front": [f"Port {i}" for i in range(1, 49)],
        "rear": [f"Port {i}" for i in range(1, 49)],
    },
    "patch-panel-fiber": {    # 48 front -> single 'Rear Splice' (48 positions)
        "id": 11, "model": "48-Pair Fiber Panel", "u": 2,
        "front": [f"Port {i}" for i in range(1, 49)],
        "rear": "Rear Splice",
    },
}

# --------------------------------------------------------------------------
# NEW objects to CREATE (absent from the demo data)
# --------------------------------------------------------------------------
NEW_DEVICE_ROLES = [
    {"name": "Firewall", "slug": "firewall", "color": "f44336"},
    {"name": "Console Server", "slug": "console-server", "color": "9c27b0"},
    {"name": "Management Switch", "slug": "management-switch", "color": "607d8b"},
    {"name": "Hypervisor Host", "slug": "hypervisor-host", "color": "4caf50"},
    {"name": "Storage", "slug": "storage", "color": "795548"},
    {"name": "Wireless AP", "slug": "wireless-ap", "color": "00bcd4"},
]

NEW_PLATFORMS = [
    {"name": "Ubuntu 22.04", "slug": "ubuntu-22-04"},
    {"name": "Windows Server 2022", "slug": "windows-server-2022"},
    {"name": "RHEL 9", "slug": "rhel-9"},
    {"name": "PAN-OS 11", "slug": "pan-os-11"},
]

# Prefix/VLAN roles are user-definable OBJECTS.
# NOTE: IPAddress.role is a FIXED choice list and canNOT be extended --
# valid values: loopback, secondary, anycast, vip, vrrp, hsrp, glbp, carp.
NEW_PREFIX_ROLES = [
    {"name": "Loopback", "slug": "loopback", "weight": 100},
    {"name": "Point-to-Point", "slug": "point-to-point", "weight": 200},
    {"name": "Server", "slug": "server", "weight": 300},
    {"name": "Guest", "slug": "guest", "weight": 400},
    {"name": "Public", "slug": "public", "weight": 500},
]

# 4 device types the demo lacks. Component templates are created with them.
NEW_DEVICE_TYPES = [
    {
        "model": "PA-3220", "slug": "pa-3220", "manufacturer": "palo-alto",
        "u_height": 2,
        "interfaces": [(f"ethernet1/{i}", "1000base-t") for i in range(1, 9)]
                      + [("management", "1000base-t", True)],
        "console": [("Console", "rj-45")],
        "power": [("PSU0", "iec-60320-c14", 350, 175),
                  ("PSU1", "iec-60320-c14", 350, 175)],
    },
    {
        "model": "CM7116-2", "slug": "cm7116-2", "manufacturer": "opengear",
        "u_height": 1,
        "interfaces": [("net1", "1000base-t"), ("net2", "1000base-t")],
        "console": [("Console", "rj-45")],
        "power": [("PSU0", "iec-60320-c14", 60, 30)],
        # console-server ports are created per-device (16)
        "console_server_ports": [f"port{i:02d}" for i in range(1, 17)],
    },
    {
        "model": "PowerEdge R650", "slug": "poweredge-r650", "manufacturer": "dell",
        "u_height": 1,
        "interfaces": [("eno1", "25gbase-x-sfp28"), ("eno2", "25gbase-x-sfp28"),
                       ("idrac", "1000base-t", True)],
        "console": [],
        "power": [("PSU0", "iec-60320-c14", 750, 375),
                  ("PSU1", "iec-60320-c14", 750, 375)],
    },
    {
        "model": "U6-Pro", "slug": "u6-pro", "manufacturer": "ubiquiti",
        "u_height": 0,      # wall/ceiling mounted; deliberately not racked
        "interfaces": [("eth0", "2.5gbase-t")],
        "console": [],
        "power": [],        # PoE powered
    },
]

# --------------------------------------------------------------------------
# Choice vocabularies (verified -- use ONLY these values)
# --------------------------------------------------------------------------
DEVICE_STATUS = ("offline", "active", "planned", "staged", "failed",
                 "inventory", "decommissioning")
SITE_STATUS = ("planned", "staging", "active", "decommissioning", "retired")
RACK_STATUS = ("reserved", "available", "planned", "active", "deprecated")
CABLE_STATUS = ("connected", "planned", "decommissioning")
PREFIX_STATUS = ("container", "active", "reserved", "deprecated")
IP_STATUS = ("active", "reserved", "deprecated", "dhcp", "slaac")
IP_ROLE = ("loopback", "secondary", "anycast", "vip", "vrrp", "hsrp",
           "glbp", "carp")          # FIXED -- cannot be extended
VLAN_STATUS = ("active", "reserved", "deprecated")
CIRCUIT_STATUS = ("planned", "provisioning", "active", "offline",
                  "deprovisioning", "decommissioned")
CLUSTER_STATUS = ("planned", "staging", "active", "decommissioning", "offline")
VM_STATUS = ("offline", "active", "planned", "staged", "failed",
             "decommissioning", "paused")
IFACE_MODE = ("access", "tagged", "tagged-all", "q-in-q")
POWER_FEED_STATUS = ("offline", "active", "planned", "failed")
POWER_FEED_TYPE = ("primary", "redundant")
JOURNAL_KIND = ("info", "success", "warning", "danger")
RACK_WIDTH = 19

CABLE_TYPE_COPPER = "cat6"
CABLE_TYPE_FIBER = "mmf-om4"
CABLE_TYPE_POWER = "power"
CONSOLE_PORT_TYPE = "rj-45"
FRONT_REAR_PORT_TYPE = "8p8c"
POWER_PORT_TYPE = "iec-60320-c14"
POWER_OUTLET_TYPE = "iec-60320-c13"

# --------------------------------------------------------------------------
# Tenant / organisation identity
# --------------------------------------------------------------------------
TENANT = {"name": "Halvorsen Logistics", "slug": "hvl"}
TENANT_GROUP = {"name": "Enterprise", "slug": "enterprise"}
REGION = {"name": "Pacific Northwest", "slug": "pacific-northwest",
          "parent_id": REGIONS_TOP["north-america"]}
