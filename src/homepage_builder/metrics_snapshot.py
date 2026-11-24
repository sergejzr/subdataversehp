"""Metrics snapshot of the data page (/at/data/): schema check, reading, writing.

The snapshot holds the public Dataverse metrics as the API returns them
(scripts/fetch_metrics.py): the collection tree, and one block of values per
published collection, fetched with parentAlias. The root block holds the
values of the whole repository. Summing, grouping and choosing which
collections get a page is left to the build, so all of that can change
without a new fetch. A second file of the same schema, kind "sample", holds
made-up numbers for the sample view: a tree with the root only.

Standard library only: the fetch script runs this without the generator's
requirements, and the build can report a broken snapshot without importing
anything else.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = 2
KINDS = ("snapshot", "sample")

REQUIRED_KEYS = {"schema", "kind", "fetched_at", "server", "dataverse_version", "tree", "collections"}
OPTIONAL_KEYS = {"comment"}
# Per collection, counting everything below it (parentAlias): datasets and
# files published, sub-collections, datasets published in the last 30 days.
COUNT_KEYS = ("datasets", "files", "dataverses", "datasets_past_30")
# Per list: item keys with their types, and the key that must be unique.
LIST_ITEMS = {
    "datasets_monthly": ({"date": str, "count": int}, "date"),
    "datasets_by_subject": ({"subject": str, "count": int}, "subject"),
    "files_by_type": ({"contenttype": str, "count": int, "size": int}, "contenttype"),
    "unique_downloads": ({"pid": str, "count": int}, "pid"),
    "dataverses_by_category": ({"category": str, "count": int}, "category"),
}
BLOCK_KEYS = {"counts", *LIST_ITEMS}
TREE_REQUIRED = {"alias", "name"}
TREE_OPTIONAL = {"id", "ownerId", "depth", "children"}
MAX_DEPTH = 20
MAX_REPORTED = 15

SERVER_PATTERN = re.compile(r"^https?://[A-Za-z0-9.-]+(?::\d+)?$")
_MONTH = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")


class MetricsSnapshotError(ValueError):
    """The snapshot is missing, unreadable or breaks the schema."""


def _is_count(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def tree_aliases(tree: dict) -> list[str]:
    """Aliases of a validated tree, root first, depth first."""
    aliases = [tree["alias"]]
    for child in tree.get("children", []):
        aliases += tree_aliases(child)
    return aliases


def _check_tree(node, where: str, depth: int, seen: set[str], errors: list[str]) -> None:
    if depth > MAX_DEPTH:
        errors.append(f"{where}: deeper than {MAX_DEPTH} levels")
        return
    if not isinstance(node, dict):
        errors.append(f"{where}: must be an object")
        return
    missing = sorted(TREE_REQUIRED - set(node))
    unknown = sorted(set(node) - TREE_REQUIRED - TREE_OPTIONAL)
    if missing:
        errors.append(f"{where}: missing {', '.join(missing)}")
    if unknown:
        errors.append(f"{where}: unknown keys {', '.join(unknown)}")
    alias = node.get("alias")
    if not (isinstance(alias, str) and alias.strip()):
        errors.append(f"{where}.alias: must be a non-empty string, got {alias!r}")
    elif alias in seen:
        errors.append(f"{where}.alias: {alias!r} appears twice")
    else:
        seen.add(alias)
        where = f"tree:{alias}"
    if "name" in node and not isinstance(node["name"], str):
        errors.append(f"{where}.name: must be a string")
    children = node.get("children", [])
    if not isinstance(children, list):
        errors.append(f"{where}.children: must be a list")
        return
    for i, child in enumerate(children, start=1):
        _check_tree(child, f"{where}.children[{i}]", depth + 1, seen, errors)


def _check_table(table, keys: tuple[str, ...], where: str, errors: list[str]) -> None:
    """An object with exactly these keys, each a whole number >= 0."""
    if not isinstance(table, dict):
        errors.append(f"{where}: must be an object")
        return
    missing = [key for key in keys if key not in table]
    unknown = sorted(set(table) - set(keys))
    if missing:
        errors.append(f"{where}: missing {', '.join(missing)}")
    if unknown:
        errors.append(f"{where}: unknown keys {', '.join(unknown)}")
    for key in keys:
        if key in table and not _is_count(table[key]):
            errors.append(f"{where}.{key}: must be a whole number >= 0, got {table[key]!r}")


def _check_list(name: str, items, where: str, errors: list[str]) -> bool:
    """Item shape and types of one list; True if the list is fine."""
    fields, unique = LIST_ITEMS[name]
    if not isinstance(items, list):
        errors.append(f"{where}: must be a list")
        return False
    before = len(errors)
    seen: set[str] = set()
    for i, item in enumerate(items, start=1):
        at = f"{where}[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{at}: must be an object")
            continue
        if set(item) != set(fields):
            errors.append(f"{at}: keys must be {', '.join(fields)}, got {', '.join(sorted(item)) or 'none'}")
            continue
        for key, kind in fields.items():
            value = item[key]
            if kind is int and not _is_count(value):
                errors.append(f"{at}.{key}: must be a whole number >= 0, got {value!r}")
            elif kind is str and not (isinstance(value, str) and value.strip()):
                errors.append(f"{at}.{key}: must be a non-empty string, got {value!r}")
        value = item[unique]
        if isinstance(value, str):
            if value in seen:
                errors.append(f"{at}: {unique} {value!r} appears twice")
            seen.add(value)
    return len(errors) == before


def _check_months(items: list[dict], where: str, errors: list[str]) -> None:
    previous = None
    for i, item in enumerate(items, start=1):
        month = item["date"]
        if not _MONTH.match(month):
            errors.append(f"{where}[{i}].date: must be YYYY-MM, got {month!r}")
            continue
        if previous is not None and month <= previous:
            errors.append(f"{where}[{i}].date: {month} is not after {previous}")
        previous = month


def _check_block(alias: str, block, errors: list[str]) -> bool:
    """One collection's values; True if the block is fine."""
    where = f"collections[{alias!r}]"
    if not isinstance(block, dict):
        errors.append(f"{where}: must be an object")
        return False
    before = len(errors)
    missing = sorted(BLOCK_KEYS - set(block))
    unknown = sorted(set(block) - BLOCK_KEYS)
    if missing:
        errors.append(f"{where}: missing {', '.join(missing)}")
    if unknown:
        errors.append(f"{where}: unknown keys {', '.join(unknown)}")
    if "counts" in block:
        _check_table(block["counts"], COUNT_KEYS, f"{where}.counts", errors)
    for name in LIST_ITEMS:
        if name in block:
            ok = _check_list(name, block[name], f"{where}.{name}", errors)
            if name == "datasets_monthly" and ok:
                _check_months(block[name], f"{where}.{name}", errors)
    if len(errors) == before:
        if block["counts"]["datasets"] and not block["datasets_monthly"]:
            errors.append(f"{where}: {block['counts']['datasets']} datasets but no datasets_monthly")
    return len(errors) == before


def validate(data, kind: str | None) -> list[str]:
    """Check data against the schema.

    kind is the kind the caller expects; None accepts either of KINDS.
    Raises MetricsSnapshotError listing the errors. Returns plausibility
    warnings, with which the page still renders.
    """
    if kind is not None and kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)} or None, got {kind!r}")
    if not isinstance(data, dict):
        raise MetricsSnapshotError("top level must be a JSON object")

    errors: list[str] = []
    missing = sorted(REQUIRED_KEYS - set(data))
    unknown = sorted(set(data) - REQUIRED_KEYS - OPTIONAL_KEYS)
    if missing:
        errors.append(f"missing keys {', '.join(missing)}")
    if unknown:
        errors.append(f"unknown keys {', '.join(unknown)}")

    schema = data.get("schema")
    if "schema" in data and (isinstance(schema, bool) or schema != SCHEMA_VERSION):
        hint = " (written by an older fetch_metrics.py: fetch again)" if schema == 1 else ""
        errors.append(f"schema must be {SCHEMA_VERSION}, got {schema!r}{hint}")
        raise MetricsSnapshotError("; ".join(errors))

    if "kind" in data:
        allowed = KINDS if kind is None else (kind,)
        if data["kind"] not in allowed:
            errors.append(f"kind must be {' or '.join(allowed)}, got {data['kind']!r}")

    if "fetched_at" in data:
        value = data["fetched_at"]
        try:
            moment = datetime.fromisoformat(value) if isinstance(value, str) else None
        except ValueError:
            moment = None
        if moment is None or moment.tzinfo is None:
            errors.append(f"fetched_at must be an ISO 8601 timestamp with time zone, got {value!r}")

    if "server" in data:
        value = data["server"]
        if not (isinstance(value, str) and SERVER_PATTERN.match(value)):
            errors.append(f"server must be a base URL like https://host, got {value!r}")

    if "dataverse_version" in data:
        value = data["dataverse_version"]
        if not (isinstance(value, str) and value.strip()):
            errors.append(f"dataverse_version must be a non-empty string, got {value!r}")

    if "comment" in data and not isinstance(data["comment"], str):
        errors.append("comment must be a string")

    aliases: list[str] = []
    if "tree" in data:
        before = len(errors)
        _check_tree(data["tree"], "tree", 0, set(), errors)
        if len(errors) == before:
            aliases = tree_aliases(data["tree"])

    blocks_ok = False
    if "collections" in data:
        collections = data["collections"]
        if not isinstance(collections, dict):
            errors.append("collections: must be an object keyed by alias")
        else:
            blocks_ok = all([_check_block(alias, block, errors) for alias, block in collections.items()])
            if aliases:
                absent = [alias for alias in aliases if alias not in collections]
                extra = sorted(set(collections) - set(aliases))
                if absent:
                    errors.append(f"collections: no values for {len(absent)} tree aliases: {', '.join(absent[:5])}")
                if extra:
                    errors.append(f"collections: {len(extra)} aliases not in the tree: {', '.join(extra[:5])}")
            if aliases and blocks_ok and aliases[0] in collections:
                if not collections[aliases[0]]["datasets_monthly"]:
                    errors.append(f"collections[{aliases[0]!r}] (root): datasets_monthly is empty, nothing to show")

    if errors:
        shown = errors[:MAX_REPORTED]
        more = f"; and {len(errors) - MAX_REPORTED} more" if len(errors) > MAX_REPORTED else ""
        raise MetricsSnapshotError("; ".join(shown) + more)

    warnings = []
    root = data["collections"][aliases[0]]
    series = root["datasets_monthly"]
    for before, after in zip(series, series[1:]):
        if after["count"] < before["count"]:
            warnings.append(
                f"root datasets_monthly falls from {before['count']} to {after['count']} in {after['date']} "
                "(metrics cache not cleared before the fetch?)"
            )
    off = [
        alias for alias, block in data["collections"].items()
        if block["datasets_monthly"] and block["datasets_monthly"][-1]["count"] != block["counts"]["datasets"]
    ]
    if off:
        warnings.append(
            f"datasets_monthly does not end at counts.datasets in {len(off)} collections: {', '.join(off[:5])}"
        )
    return warnings


def load(path: Path, kind: str | None) -> tuple[dict, list[str]]:
    """Read and validate a snapshot; returns (data, warnings)."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise MetricsSnapshotError(f"{path.name} is missing") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise MetricsSnapshotError(f"{path.name} cannot be read: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MetricsSnapshotError(f"{path.name} is not valid JSON: {exc}") from exc
    try:
        warnings = validate(data, kind)
    except MetricsSnapshotError as exc:
        raise MetricsSnapshotError(f"{path.name}: {exc}") from None
    return data, warnings


def dump(data: dict, path: Path) -> None:
    """Write data as stable, sorted JSON. Atomic: a failure leaves the old file as it was."""
    text = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
