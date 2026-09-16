"""Static validation of the blueprint -- run BEFORE any live seeding.

Catches the class of mistake that would otherwise fail deep inside a live run
with an opaque HTTP 400: dangling references, invalid choice values, VID
collisions with the v4 dataset, and rack geometry errors.

RACK GEOMETRY: in NetBox `position` is the LOWEST-numbered unit occupied, and a
device extends UPWARD. A 2U device at U34 occupies U34 and U35. Getting this
backwards both invents phantom overlaps and hides real ones, so it is asserted
explicitly here.

    ./venv/bin/python -m scripts.seed_benchmark_v5.validate
"""

from __future__ import annotations

import collections
import sys

from . import blueprint as B
from . import config as C


def unit_span(position: int, u_height: float) -> range:
    """Units occupied by a device: upward from `position`."""
    h = max(int(u_height), 1)          # 0U devices are not rack-mounted
    return range(position, position + h)


def validate() -> tuple[list[str], list[str]]:
    errs: list[str] = []
    warn: list[str] = []

    type_keys = set(C.REUSE_DEVICE_TYPES) | {d["slug"] for d in C.NEW_DEVICE_TYPES}
    role_keys = set(C.DEVICE_ROLES) | {r["slug"] for r in C.NEW_DEVICE_ROLES}
    platform_keys = {p["slug"] for p in C.NEW_PLATFORMS}
    sites = {s["slug"] for s in B.SITES}
    locs = {(s["slug"], l) for s in B.SITES for l in s["locations"]}
    racks = {r["name"] for r in B.RACKS}
    rack_site = {r["name"]: r["site"] for r in B.RACKS}
    rack_h = {r["name"]: r["u_height"] for r in B.RACKS}
    dev_names = [d["name"] for d in B.DEVICES]
    vm_names = {v[0] for v in B.VMS}

    u_height = {k: v["u"] for k, v in C.REUSE_DEVICE_TYPES.items()}
    u_height.update({d["slug"]: d["u_height"] for d in C.NEW_DEVICE_TYPES})

    # -- duplicates ---------------------------------------------------------
    for n, c in collections.Counter(dev_names).items():
        if c > 1:
            errs.append(f"duplicate device name: {n} (x{c})")

    # -- device references + choices ---------------------------------------
    for d in B.DEVICES:
        n = d["name"]
        if d["type"] not in type_keys:
            errs.append(f"{n}: unknown device type {d['type']!r}")
        if d["role"] not in role_keys:
            errs.append(f"{n}: unknown role {d['role']!r}")
        if d["site"] not in sites:
            errs.append(f"{n}: unknown site {d['site']!r}")
        if d.get("status") and d["status"] not in C.DEVICE_STATUS:
            errs.append(f"{n}: invalid status {d['status']!r}")
        if d.get("platform") and d["platform"] not in platform_keys:
            errs.append(f"{n}: unknown platform {d['platform']!r}")
        rk = d.get("rack")
        if rk:
            if rk not in racks:
                errs.append(f"{n}: unknown rack {rk!r}")
            elif rack_site[rk] != d["site"]:
                errs.append(f"{n}: rack {rk} belongs to {rack_site[rk]}, not {d['site']}")
        if d.get("position") is not None and not rk:
            errs.append(f"{n}: has position but no rack")

    # -- racks / locations --------------------------------------------------
    for r in B.RACKS:
        if r["site"] not in sites:
            errs.append(f"rack {r['name']}: unknown site {r['site']!r}")
        if (r["site"], r["location"]) not in locs:
            errs.append(f"rack {r['name']}: unknown location {r['location']!r}")
        if r["status"] not in C.RACK_STATUS:
            errs.append(f"rack {r['name']}: invalid status {r['status']!r}")

    # -- v4 collision guard -------------------------------------------------
    for vid, name in B.VLANS_BRANCH + B.VLANS_DC:
        if vid in C.FORBIDDEN_VIDS:
            errs.append(f"VID {vid} ({name}) is FORBIDDEN -- collides with the v4 dataset")

    # -- circuits -----------------------------------------------------------
    known_ctypes = set(C.CIRCUIT_TYPES) | {t["slug"] for t in B.NEW_CIRCUIT_TYPES}
    providers = {p["slug"] for p in B.PROVIDERS}
    for cid, prov, ctype, site, status, _rate, cable in B.CIRCUITS:
        if prov not in providers:
            errs.append(f"circuit {cid}: unknown provider {prov!r}")
        if ctype not in known_ctypes:
            errs.append(f"circuit {cid}: unknown type {ctype!r}")
        if site not in sites:
            errs.append(f"circuit {cid}: unknown site {site!r}")
        if status not in C.CIRCUIT_STATUS:
            errs.append(f"circuit {cid}: invalid status {status!r}")
        if cable and cable not in dev_names:
            errs.append(f"circuit {cid}: cables to unknown device {cable!r}")

    # -- power --------------------------------------------------------------
    panels = {p["name"] for p in B.POWER_PANELS}
    for p in B.POWER_PANELS:
        if p["site"] not in sites:
            errs.append(f"panel {p['name']}: unknown site")
        if (p["site"], p["location"]) not in locs:
            errs.append(f"panel {p['name']}: unknown location {p['location']!r}")
    for name, panel, rack, ftype, status, _v, _a in B.POWER_FEEDS:
        if panel not in panels:
            errs.append(f"feed {name}: unknown panel {panel!r}")
        if rack not in racks:
            errs.append(f"feed {name}: unknown rack {rack!r}")
        if ftype not in C.POWER_FEED_TYPE:
            errs.append(f"feed {name}: invalid type {ftype!r}")
        if status not in C.POWER_FEED_STATUS:
            errs.append(f"feed {name}: invalid status {status!r}")

    # -- virtualization -----------------------------------------------------
    cluster_names = {c["name"] for c in B.CLUSTERS}
    for c in B.CLUSTERS:
        if c["status"] not in C.CLUSTER_STATUS:
            errs.append(f"cluster {c['name']}: invalid status")
        if c["site"] not in sites:
            errs.append(f"cluster {c['name']}: unknown site")
    for name, cl, host, _cpu, _mem, _disk, status, platform in B.VMS:
        if cl not in cluster_names:
            errs.append(f"vm {name}: unknown cluster {cl!r}")
        if host and host not in dev_names:
            errs.append(f"vm {name}: unknown host device {host!r}")
        if status not in C.VM_STATUS:
            errs.append(f"vm {name}: invalid status {status!r}")
        if platform not in platform_keys:
            errs.append(f"vm {name}: unknown platform {platform!r}")

    # -- prefixes -----------------------------------------------------------
    for pfx, status, role, site, vid, _fill, note in B.PREFIX_PLAN:
        if status not in C.PREFIX_STATUS:
            errs.append(f"prefix {pfx}: invalid status {status!r}")
        if site and site not in sites:
            errs.append(f"prefix {pfx}: unknown site {site!r}")
        if vid and vid in C.FORBIDDEN_VIDS:
            errs.append(f"prefix {pfx}: bound to FORBIDDEN VID {vid}")

    # -- defect answer-key references --------------------------------------
    known = set(dev_names) | vm_names
    for did, d in B.DEFECTS.items():
        for obj in d["objects"]:
            tok = obj.split()[0].rstrip(",")
            if tok in known:
                continue
            if tok[0].isdigit() or tok.startswith(("HVL", "DC1", "EV-", "CF-",
                                                   "RB-", "SW-", "192.", "10.")):
                continue
            warn.append(f"{did}: {tok!r} is not a known device or VM name")

    # -- rack geometry (upward spans) --------------------------------------
    occ: dict[str, dict[int, str]] = collections.defaultdict(dict)
    for d in B.DEVICES:
        rk, pos = d.get("rack"), d.get("position")
        if not rk or pos is None:
            continue
        for u in unit_span(pos, u_height[d["type"]]):
            if u in occ[rk]:
                errs.append(f"RACK OVERLAP {rk} U{u}: {d['name']} vs {occ[rk][u]}")
            occ[rk][u] = d["name"]
            if u < 1 or u > rack_h[rk]:
                errs.append(f"{d['name']} occupies U{u}, outside {rk} (1..{rack_h[rk]})")

    for res in B.RACK_RESERVATIONS:
        rk = res["rack"]
        if rk not in racks:
            errs.append(f"reservation: unknown rack {rk!r}")
            continue
        for u in res["units"]:
            if u in occ[rk]:
                errs.append(f"RESERVATION CLASH {rk} U{u}: occupied by {occ[rk][u]}")
            if u < 1 or u > rack_h[rk]:
                errs.append(f"reservation U{u} outside {rk} (1..{rack_h[rk]})")

    return errs, warn


def rack_fill_report() -> str:
    """Rack utilization spread -- deliberate variety is the point."""
    u_height = {k: v["u"] for k, v in C.REUSE_DEVICE_TYPES.items()}
    u_height.update({d["slug"]: d["u_height"] for d in C.NEW_DEVICE_TYPES})
    used: dict[str, int] = collections.defaultdict(int)
    for d in B.DEVICES:
        if d.get("rack") and d.get("position") is not None:
            used[d["rack"]] += max(int(u_height[d["type"]]), 1)
    reserved: dict[str, int] = collections.defaultdict(int)
    for r in B.RACK_RESERVATIONS:
        reserved[r["rack"]] += len(r["units"])

    lines = [f"  {'rack':14}{'U':>4}{'dev':>5}{'resv':>6}{'total':>7}{'fill':>7}"]
    for r in B.RACKS:
        n, h = r["name"], r["u_height"]
        tot = used[n] + reserved[n]
        lines.append(f"  {n:14}{h:>4}{used[n]:>5}{reserved[n]:>6}{tot:>7}{tot / h:>6.0%}")
    return "\n".join(lines)


def main() -> int:
    errs, warn = validate()
    print(f"blueprint: {len(B.DEVICES)} devices, {len(B.RACKS)} racks, "
          f"{len(B.CIRCUITS)} circuits, {len(B.VMS)} VMs, "
          f"{len(B.PREFIX_PLAN)} prefixes, {len(B.DEFECTS)} defects")
    print("\nrack fill (reservations count toward NetBox utilization):")
    print(rack_fill_report())
    print(f"\nERRORS ({len(errs)}):")
    for e in errs:
        print(f"  x {e}")
    print(f"WARNINGS ({len(warn)}):")
    for w in warn:
        print(f"  ! {w}")
    if errs:
        print("\nVALIDATION FAILED -- fix before seeding.")
        return 1
    print("\nvalidation OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
