#!/usr/bin/env python3
"""Fetch the public Dataverse metrics for the data page (/at/data/) into a snapshot.

Paths are relative to the generator root, so it runs from anywhere:

    python3 scripts/fetch_metrics.py
        test system -> templates/landing/metrics.json
    python3 scripts/fetch_metrics.py --check templates/landing/metrics.sample.json
        only check a snapshot or sample file

Clear the metrics cache on the server right before a fetch. Dataverse caches
current values for up to seven days and past months for good; on the server:
curl -X DELETE http://localhost:8080/api/admin/clearMetricsCache

The snapshot is written only if every request succeeds and the result passes
the schema check (src/homepage_builder/metrics_snapshot.py). Otherwise the old
file stays as it is. Standard library only. Exit status 0: written or valid,
1: error.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src" / "homepage_builder"))

import metrics_snapshot  # noqa: E402  standard library only, works without the requirements

DEFAULT_SERVER = "https://datapublication-nrw-test.hrz.uni-bonn.de"
DEFAULT_OUTPUT = ROOT / "templates" / "landing" / "metrics.json"
METRICS = "/api/info/metrics/"
USER_AGENT = "datapublication-fetch-metrics/1"
PREFIX = "[fetch_metrics]"


class FetchError(RuntimeError):
    """A request failed or the answer was not {"status": "OK", "data": ...}."""


def get_data(server: str, path: str, timeout: float):
    """The data part of one API answer, requested as JSON."""
    url = server + path
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        raise FetchError(f"{url}: HTTP {exc.code} {exc.reason}") from exc
    except OSError as exc:  # URLError, timeouts, refused connections
        raise FetchError(f"{url}: {exc}") from exc
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise FetchError(f"{url}: answer is not JSON ({exc})") from exc
    if not isinstance(payload, dict) or payload.get("status") != "OK" or "data" not in payload:
        raise FetchError(f"{url}: unexpected answer {json.dumps(payload)[:200]}")
    return payload["data"]


def fetch(server: str, timeout: float) -> dict:
    """All values the page shows, as the API returns them. Accounts are left out on purpose."""

    def get(path: str):
        return get_data(server, path, timeout)

    def count(name: str):
        data = get(METRICS + name)
        return data.get("count") if isinstance(data, dict) else data

    fetched_at = datetime.now().astimezone().isoformat(timespec="seconds")
    version = get("/api/info/version")
    return {
        "schema": metrics_snapshot.SCHEMA_VERSION,
        "kind": "snapshot",
        "fetched_at": fetched_at,
        "server": server,
        "dataverse_version": version.get("version") if isinstance(version, dict) else version,
        "counts": {name: count(name) for name in metrics_snapshot.COUNT_KEYS},
        "datasets_monthly": get(METRICS + "datasets/monthly"),
        "datasets_by_subject": get(METRICS + "datasets/bySubject"),
        "files_by_type": get(METRICS + "files/byType"),
        "unique_downloads": get(METRICS + "uniquedownloads"),
    }


def stable_order(data: dict) -> None:
    """Sort the lists without a natural order, so a new snapshot diffs cleanly against the old one."""
    data["datasets_by_subject"].sort(key=lambda item: (-item["count"], item["subject"]))
    data["files_by_type"].sort(key=lambda item: item["contenttype"])
    data["unique_downloads"].sort(key=lambda item: item["pid"])


def summary(data: dict) -> str:
    months = data["datasets_monthly"]
    downloads = data["unique_downloads"]
    size = sum(item["size"] for item in data["files_by_type"])
    return (
        f"datasets {data['counts']['datasets']}, files {data['counts']['files']}, {size / 1e6:.1f} MB, "
        f"months {months[0]['date']}..{months[-1]['date']}, subjects {len(data['datasets_by_subject'])}, "
        f"content types {len(data['files_by_type'])}, "
        f"unique downloads {sum(item['count'] for item in downloads)} ({len(downloads)} datasets listed)"
    )


def check(path: Path) -> int:
    try:
        data, warnings = metrics_snapshot.load(path, None)
    except metrics_snapshot.MetricsSnapshotError as exc:
        print(f"{PREFIX} ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"{PREFIX} {path}: valid {data['kind']}, {data['fetched_at']}")
    print(f"{PREFIX} {summary(data)}")
    for warning in warnings:
        print(f"{PREFIX} Warning: {warning}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--server", default=DEFAULT_SERVER, help=f"base URL (default {DEFAULT_SERVER})")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="snapshot file (default %(default)s)")
    parser.add_argument("--timeout", type=float, default=30.0, help="seconds per request (default %(default)s)")
    parser.add_argument("--check", type=Path, metavar="FILE", help="only check an existing snapshot or sample file")
    args = parser.parse_args(argv)

    if args.check:
        return check(args.check)

    server = args.server.rstrip("/")
    if not metrics_snapshot.SERVER_PATTERN.match(server):
        print(f"{PREFIX} ERROR: --server must be a base URL like https://host, got {args.server!r}", file=sys.stderr)
        return 1
    try:
        data = fetch(server, args.timeout)
        warnings = metrics_snapshot.validate(data, "snapshot")
        stable_order(data)
        metrics_snapshot.dump(data, args.output)
    except (FetchError, metrics_snapshot.MetricsSnapshotError, OSError) as exc:
        print(f"{PREFIX} ERROR: {exc}", file=sys.stderr)
        print(f"{PREFIX} {args.output} unchanged", file=sys.stderr)
        return 1

    print(f"{PREFIX} {server}, Dataverse {data['dataverse_version']}, {data['fetched_at']}")
    print(f"{PREFIX} {summary(data)}")
    for warning in warnings:
        print(f"{PREFIX} Warning: {warning}", file=sys.stderr)
    print(f"{PREFIX} written {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
