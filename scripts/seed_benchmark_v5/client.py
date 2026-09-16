"""Idempotent NetBox write client for the benchmark-v5 seed.

Deliberately small and explicit rather than using pynetbox, because the seed
needs three things pynetbox does not give directly:

  * get-or-create by NATURAL KEY (pynetbox has no upsert)
  * a real --dry-run that performs zero writes
  * loud, readable failures (NetBox 4xx bodies say exactly what is wrong, and
    bulk POSTs are all-or-nothing, so a silent failure would corrupt a layer)

All writes go through the seeder token. Reads used for verification should use
the read-only agent token instead -- see verify.py.
"""

from __future__ import annotations

import sys
from typing import Any, Iterable

import httpx

from . import config


class SeedError(RuntimeError):
    pass


class NetBoxSeeder:
    def __init__(self, *, dry_run: bool = False, timeout: float = 60.0) -> None:
        self.dry_run = dry_run
        self.url = config.netbox_url()
        self._c = httpx.Client(
            base_url=self.url,
            headers={
                "Authorization": f"Token {config.seed_token()}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
        self.created: dict[str, int] = {}
        self.reused: dict[str, int] = {}
        self.patched: dict[str, int] = {}
        self._fake_id = -1

    # -- plumbing ----------------------------------------------------------
    def _tally(self, d: dict[str, int], ep: str, n: int = 1) -> None:
        d[ep] = d.get(ep, 0) + n

    def _check(self, r: httpx.Response, ep: str, payload: Any) -> Any:
        if r.status_code in (200, 201, 204):
            return r.json() if r.content else None
        raise SeedError(
            f"{r.request.method} /api/{ep}/ -> HTTP {r.status_code}\n"
            f"  payload: {str(payload)[:400]}\n"
            f"  response: {r.text[:600]}"
        )

    def get(self, ep: str, **params: Any) -> list[dict]:
        # In dry-run, earlier layers hand out FAKE negative ids for objects
        # that were never really created. Filtering on one makes NetBox reject
        # the query ("-3 is not one of the available choices"), so treat it as
        # "not found" -- which is the truth: in a dry run it does not exist.
        # Guarding here (rather than only in get_or_create) covers every
        # caller, including layers that look up directly.
        if self.dry_run and any(
            isinstance(v, int) and v < 0 for v in params.values()
        ):
            return []
        r = self._c.get(f"/api/{ep}/", params={"limit": 500, **params})
        return self._check(r, ep, params)["results"]

    def count(self, ep: str, **params: Any) -> int:
        r = self._c.get(f"/api/{ep}/", params={"limit": 1, **params})
        return self._check(r, ep, params)["count"]

    # -- writes ------------------------------------------------------------
    def create(self, ep: str, payload: dict) -> dict:
        if self.dry_run:
            self._tally(self.created, ep)
            self._fake_id -= 1
            return {"id": self._fake_id, **payload, "_dry_run": True}
        r = self._c.post(f"/api/{ep}/", json=payload)
        obj = self._check(r, ep, payload)
        self._tally(self.created, ep)
        return obj

    def create_many(self, ep: str, payloads: list[dict]) -> list[dict]:
        """Bulk create. NetBox bulk POSTs are all-or-nothing."""
        if not payloads:
            return []
        if self.dry_run:
            self._tally(self.created, ep, len(payloads))
            out = []
            for p in payloads:
                self._fake_id -= 1
                out.append({"id": self._fake_id, **p, "_dry_run": True})
            return out
        r = self._c.post(f"/api/{ep}/", json=payloads)
        objs = self._check(r, ep, payloads[:2])
        self._tally(self.created, ep, len(objs))
        return objs

    def patch(self, ep: str, obj_id: int, payload: dict) -> dict:
        if self.dry_run:
            self._tally(self.patched, ep)
            return {"id": obj_id, **payload, "_dry_run": True}
        r = self._c.patch(f"/api/{ep}/{obj_id}/", json=payload)
        obj = self._check(r, ep, payload)
        self._tally(self.patched, ep)
        return obj

    def delete(self, ep: str, obj_id: int) -> None:
        if self.dry_run:
            return
        r = self._c.delete(f"/api/{ep}/{obj_id}/")
        self._check(r, ep, {"id": obj_id})

    # -- idempotency -------------------------------------------------------
    def get_or_create(self, ep: str, *, match: dict, payload: dict) -> dict:
        """Look up by natural key; create only if absent.

        `match` MUST narrow to at most one object. NetBox silently ignores
        unknown filter params and returns everything, so a bad filter would
        make this return an unrelated object -- we assert the match instead.
        """
        # In dry-run, earlier layers hand out FAKE negative ids for objects
        # that were never really created. Filtering on one of those makes
        # NetBox reject the query ("-30 is not one of the available choices"),
        # so skip the lookup and simulate the create directly. Real runs are
        # unaffected: ids are always positive there.
        if self.dry_run and any(
            isinstance(v, int) and v < 0 for v in match.values()
        ):
            return self.create(ep, payload)

        existing = self.get(ep, **match)
        if len(existing) > 1:
            raise SeedError(
                f"match {match} on /api/{ep}/ returned {len(existing)} objects; "
                "refusing to guess (is the filter name valid?)"
            )
        if existing:
            self._tally(self.reused, ep)
            return existing[0]
        return self.create(ep, payload)

    def tagged(self, payload: dict) -> dict:
        """Apply the seed marker tag, preserving any explicit tags."""
        tags = list(payload.get("tags") or [])
        if config.SEED_TAG["slug"] not in [
            t.get("slug") if isinstance(t, dict) else t for t in tags
        ]:
            tags.append({"slug": config.SEED_TAG["slug"]})
        return {**payload, "tags": tags}

    # -- reporting ---------------------------------------------------------
    def summary(self) -> str:
        def fmt(title: str, d: dict[str, int]) -> str:
            if not d:
                return f"  {title}: none"
            rows = "\n".join(
                f"    {k:36} {v:>5}" for k, v in sorted(d.items(), key=lambda x: -x[1])
            )
            return f"  {title}: {sum(d.values())} total\n{rows}"

        mode = "DRY RUN (no writes performed)" if self.dry_run else "LIVE"
        return "\n".join([
            f"\n=== seed summary [{mode}] ===",
            fmt("created", self.created),
            fmt("reused", self.reused),
            fmt("patched", self.patched),
        ])

    def close(self) -> None:
        self._c.close()


def preflight(seeder: NetBoxSeeder) -> None:
    """Fail fast if the instance is not in the expected state."""
    problems: list[str] = []

    # writable?
    r = seeder._c.get("/api/status/")
    if r.status_code != 200:
        problems.append(f"/api/status/ -> HTTP {r.status_code} (worker/redis down?)")

    # Retention MUST be 0, or seeded change history is silently pruned at 90
    # days by the housekeeping container -- destroying the ground truth long
    # after the benchmark is built.
    #
    # NOTE: there is NO API endpoint for this in 4.3 (/api/core/config/,
    # /api/extras/config/ and /api/core/config-revisions/ all return 404 --
    # verified 2026-09-16). The value lives in dynamic config and is only
    # readable through the Django app, so we shell into the container.
    import shutil
    import subprocess

    if shutil.which("docker"):
        probe = subprocess.run(
            ["docker", "exec", "netbox-docker-netbox-1",
             "/opt/netbox/venv/bin/python", "/opt/netbox/netbox/manage.py",
             "shell", "-c",
             "from netbox.config import get_config; c=get_config();"
             "print('RETENTION', c.CHANGELOG_RETENTION, c.JOB_RETENTION)"],
            capture_output=True, text=True, timeout=120,
        )
        line = next(
            (ln for ln in probe.stdout.splitlines() if ln.startswith("RETENTION")),
            None,
        )
        if line is None:
            problems.append(
                f"could not read CHANGELOG_RETENTION (rc={probe.returncode}): "
                f"{probe.stderr.strip()[:200]}"
            )
        else:
            _, changelog, job = line.split()
            if changelog != "0":
                problems.append(
                    f"CHANGELOG_RETENTION={changelog} (expected 0; seeded history "
                    "would be pruned after that many days)"
                )
            if job != "0":
                problems.append(f"JOB_RETENTION={job} (expected 0)")
    else:
        problems.append("docker not available -- cannot verify CHANGELOG_RETENTION")

    # v4 collision guard: VID 100 must remain Dunder-Mifflin's alone
    for vid in config.FORBIDDEN_VIDS:
        owners = {
            (v.get("tenant") or {}).get("slug")
            for v in seeder.get("ipam/vlans", vid=vid)
        }
        if owners - {"dunder-mifflin", None}:
            problems.append(f"VID {vid} already used outside Dunder-Mifflin: {owners}")

    if problems:
        print("PREFLIGHT FAILED:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        raise SeedError("preflight checks failed")
    print("preflight OK")


def chunked(items: Iterable, size: int = 100):
    buf: list = []
    for it in items:
        buf.append(it)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf
