#!/usr/bin/env python3
"""Fetch the public Dataverse metrics for the data page (/at/data/) into a snapshot.

Paths are relative to the generator root, so it runs from anywhere:

    python3 scripts/fetch_metrics.py
        test system -> templates/landing/metrics.json
    python3 scripts/fetch_metrics.py --check templates/landing/metrics.sample.json
        only check a snapshot or sample file

Fetches the collection tree, then the values of every published collection
with parentAlias (the root collection stands for the whole repository): about
nine requests per collection, a few in parallel.

Clear the metrics cache on the server right before a fetch. Dataverse caches
current values for up to seven days and past months for good; on the server:
curl -sS -o /dev/null -w '%{http_code}\\n' -X DELETE http://localhost:8080/api/admin/clearMetricsCache

The snapshot is written only if every request succeeds and the result passes
the schema check (src/homepage_builder/metrics_snapshot.py). Otherwise the old
file stays as it is. Standard library only. Exit status 0: written or valid,
1: error.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src" / "homepage_builder"))

import metrics_snapshot  # noqa: E402  standard library only, works without the requirements

DEFAULT_SERVER = "https://datapublication-nrw-test.hrz.uni-bonn.de"
DEFAULT_OUTPUT = ROOT / "templates" / "landing" / "metrics.json"
METRICS = "/api/info/metrics/"
# Block key -> endpoint below METRICS, each with ?parentAlias=<alias>.
COUNTS = {
    "datasets": "datasets",
    "files": "files",
    "dataverses": "dataverses",
    "datasets_past_30": "datasets/pastDays/30",
}
LISTS = {
    "datasets_by_subject": "datasets/bySubject",
    "files_by_type": "files/byType",
    "unique_downloads": "uniquedownloads",
    "dataverses_by_category": "dataverses/byCategory",
}
USER_AGENT = "datapublication-fetch-metrics/2"
PREFIX = "[fetch_metrics]"
RETRY_DELAY = 2.0


class FetchError(RuntimeError):
    """A request failed or the answer was not {"status": "OK", "data": ...}."""


def get_data(server: str, path: str, timeout: float):
    """The data part of one API answer, requested as JSON. Retried once after
    a server error or a network problem, never after a 4xx."""
    url = server + path
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
            break
        except urllib.error.HTTPError as exc:
            if exc.code < 500 or attempt == 2:
                raise FetchError(f"{url}: HTTP {exc.code} {exc.reason}") from exc
        except OSError as exc:  # URLError, timeouts, refused connections
            if attempt == 2:
                raise FetchError(f"{url}: {exc}") from exc
        time.sleep(RETRY_DELAY)
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise FetchError(f"{url}: answer is not JSON ({exc})") from exc
    if not isinstance(payload, dict) or payload.get("status") != "OK" or "data" not in payload:
        raise FetchError(f"{url}: unexpected answer {json.dumps(payload)[:200]}")
    return payload["data"]


def fetch_block(server: str, alias: str, timeout: float) -> dict:
    """All values of one collection, everything below it included."""
    query = "?parentAlias=" + urllib.parse.quote(alias, safe="")

    def get(endpoint: str):
        return get_data(server, METRICS + endpoint + query, timeout)

    counts = {}
    for key, endpoint in COUNTS.items():
        data = get(endpoint)
        counts[key] = data.get("count") if isinstance(data, dict) else data
    block = {"counts": counts}
    # Dataverse 6.12 answers datasets/monthly with HTTP 500 for a collection
    # without published datasets: there is no series to fetch then.
    block["datasets_monthly"] = get("datasets/monthly") if counts["datasets"] else []
    for key, endpoint in LISTS.items():
        block[key] = get(endpoint)
    return block


def fetch(server: str, timeout: float, workers: int) -> dict:
    """The snapshot: tree and one block per published collection. Accounts are left out on purpose."""
    fetched_at = datetime.now().astimezone().isoformat(timespec="seconds")
    version = get_data(server, "/api/info/version", timeout)
    tree = get_data(server, METRICS + "tree", timeout)
    try:
        aliases = metrics_snapshot.tree_aliases(tree)
    except (KeyError, TypeError, AttributeError) as exc:
        raise FetchError(f"tree has an unexpected shape ({exc!r})") from exc
    print(f"{PREFIX} {len(aliases)} collections, fetching their values ...", flush=True)

    collections: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_block, server, alias, timeout): alias for alias in aliases}
        done, pending = wait(futures, return_when=FIRST_EXCEPTION)
        for future in pending:
            future.cancel()
        for future in done:
            exc = future.exception()
            if exc:
                raise exc if isinstance(exc, FetchError) else FetchError(f"{futures[future]}: {exc!r}")
            collections[futures[future]] = future.result()
    return {
        "schema": metrics_snapshot.SCHEMA_VERSION,
        "kind": "snapshot",
        "fetched_at": fetched_at,
        "server": server,
        "dataverse_version": version.get("version") if isinstance(version, dict) else version,
        "tree": tree,
        "collections": collections,
    }


def stable_order(data: dict) -> None:
    """Sort the lists without a natural order, so a new snapshot diffs cleanly against the old one."""
    def sort_tree(node: dict) -> None:
        node.get("children", []).sort(key=lambda child: child["alias"])
        for child in node.get("children", []):
            sort_tree(child)

    sort_tree(data["tree"])
    for block in data["collections"].values():
        block["datasets_by_subject"].sort(key=lambda item: (-item["count"], item["subject"]))
        block["files_by_type"].sort(key=lambda item: item["contenttype"])
        block["unique_downloads"].sort(key=lambda item: item["pid"])
        block["dataverses_by_category"].sort(key=lambda item: (-item["count"], item["category"]))


def summary(data: dict) -> str:
    root = data["collections"][data["tree"]["alias"]]
    months = root["datasets_monthly"]
    downloads = root["unique_downloads"]
    size = sum(item["size"] for item in root["files_by_type"])
    return (
        f"{len(data['collections'])} collections; whole repository: datasets {root['counts']['datasets']} "
        f"(+{root['counts']['datasets_past_30']} in 30 days), files {root['counts']['files']}, {size / 1e6:.1f} MB, "
        f"months {months[0]['date']}..{months[-1]['date']}, subjects {len(root['datasets_by_subject'])}, "
        f"content types {len(root['files_by_type'])}, sub-collections {root['counts']['dataverses']}, "
        f"unique downloads {sum(item['count'] for item in downloads)}"
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
    parser.add_argument("--workers", type=int, default=4, help="parallel requests (default %(default)s)")
    parser.add_argument("--check", type=Path, metavar="FILE", help="only check an existing snapshot or sample file")
    args = parser.parse_args(argv)

    if args.check:
        return check(args.check)

    server = args.server.rstrip("/")
    if not metrics_snapshot.SERVER_PATTERN.match(server):
        print(f"{PREFIX} ERROR: --server must be a base URL like https://host, got {args.server!r}", file=sys.stderr)
        return 1
    if not 1 <= args.workers <= 8:
        print(f"{PREFIX} ERROR: --workers must be 1 to 8, got {args.workers}", file=sys.stderr)
        return 1
    started = time.monotonic()
    try:
        data = fetch(server, args.timeout, args.workers)
        warnings = metrics_snapshot.validate(data, "snapshot")
        stable_order(data)
        metrics_snapshot.dump(data, args.output)
    except KeyboardInterrupt:
        print(f"\n{PREFIX} interrupted, {args.output} unchanged", file=sys.stderr)
        return 1
    except (FetchError, metrics_snapshot.MetricsSnapshotError, OSError) as exc:
        print(f"{PREFIX} ERROR: {exc}", file=sys.stderr)
        print(f"{PREFIX} {args.output} unchanged", file=sys.stderr)
        return 1

    print(f"{PREFIX} {server}, Dataverse {data['dataverse_version']}, {data['fetched_at']}, "
          f"{time.monotonic() - started:.0f} s")
    print(f"{PREFIX} {summary(data)}")
    for warning in warnings:
        print(f"{PREFIX} Warning: {warning}", file=sys.stderr)
    print(f"{PREFIX} written {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
