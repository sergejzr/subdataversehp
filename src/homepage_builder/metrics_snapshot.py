"""Metrics snapshot of the data page (/at/data/): schema check, reading, writing.

The snapshot holds the public Dataverse metrics as the API returns them
(scripts/fetch_metrics.py). Summing and grouping is left to the build, so the
groups can change without a new fetch. A second file of the same schema, kind
"sample", holds made-up numbers for the sample view of the page.

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

SCHEMA_VERSION = 1
KINDS = ("snapshot", "sample")

REQUIRED_KEYS = {
    "schema", "kind", "fetched_at", "server", "dataverse_version", "counts",
    "datasets_monthly", "datasets_by_subject", "files_by_type", "unique_downloads",
}
# comment: free text for whoever opens the file. areas: set-up and accepted
# university areas; a snapshot takes them from status.csv at build time, a
# sample brings its own made-up values.
OPTIONAL_KEYS = {"comment", "areas"}
COUNT_KEYS = ("datasets", "files")
AREA_KEYS = ("set_up", "accepted")
# Per list: item keys with their types, and the key that must be unique.
LIST_ITEMS = {
    "datasets_monthly": ({"date": str, "count": int}, "date"),
    "datasets_by_subject": ({"subject": str, "count": int}, "subject"),
    "files_by_type": ({"contenttype": str, "count": int, "size": int}, "contenttype"),
    "unique_downloads": ({"pid": str, "count": int}, "pid"),
}

SERVER_PATTERN = re.compile(r"^https?://[A-Za-z0-9.-]+(?::\d+)?$")
_MONTH = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")


class MetricsSnapshotError(ValueError):
    """The snapshot is missing, unreadable or breaks the schema."""


def _is_count(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


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


def _check_list(name: str, items, errors: list[str]) -> bool:
    """Item shape and types of one list; True if the list is fine."""
    fields, unique = LIST_ITEMS[name]
    if not isinstance(items, list):
        errors.append(f"{name}: must be a list")
        return False
    before = len(errors)
    seen: set[str] = set()
    for i, item in enumerate(items, start=1):
        where = f"{name}[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{where}: must be an object")
            continue
        if set(item) != set(fields):
            errors.append(f"{where}: keys must be {', '.join(fields)}, got {', '.join(sorted(item)) or 'none'}")
            continue
        for key, kind in fields.items():
            value = item[key]
            if kind is int and not _is_count(value):
                errors.append(f"{where}.{key}: must be a whole number >= 0, got {value!r}")
            elif kind is str and not (isinstance(value, str) and value.strip()):
                errors.append(f"{where}.{key}: must be a non-empty string, got {value!r}")
        value = item[unique]
        if isinstance(value, str):
            if value in seen:
                errors.append(f"{where}: {unique} {value!r} appears twice")
            seen.add(value)
    return len(errors) == before


def _check_months(items: list[dict], errors: list[str]) -> None:
    if not items:
        errors.append("datasets_monthly: is empty, the page has no series to show")
        return
    previous = None
    for i, item in enumerate(items, start=1):
        month = item["date"]
        if not _MONTH.match(month):
            errors.append(f"datasets_monthly[{i}].date: must be YYYY-MM, got {month!r}")
            continue
        if previous is not None and month <= previous:
            errors.append(f"datasets_monthly[{i}].date: {month} is not after {previous}")
        previous = month


def validate(data, kind: str | None) -> list[str]:
    """Check data against the schema.

    kind is the kind the caller expects; None accepts either of KINDS.
    Raises MetricsSnapshotError listing every error. Returns plausibility
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
        errors.append(f"schema must be {SCHEMA_VERSION}, got {schema!r}")

    actual_kind = data.get("kind")
    if "kind" in data:
        allowed = KINDS if kind is None else (kind,)
        if actual_kind not in allowed:
            errors.append(f"kind must be {' or '.join(allowed)}, got {actual_kind!r}")

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

    if "counts" in data:
        _check_table(data["counts"], COUNT_KEYS, "counts", errors)

    months_ok = False
    for name in LIST_ITEMS:
        if name in data:
            ok = _check_list(name, data[name], errors)
            if name == "datasets_monthly" and ok:
                before = len(errors)
                _check_months(data[name], errors)
                months_ok = len(errors) == before

    if actual_kind == "sample" and "areas" not in data:
        errors.append("areas: a sample needs its own areas (set_up, accepted)")
    if actual_kind == "snapshot" and "areas" in data:
        errors.append("areas: a snapshot takes the areas from status.csv, not from the file")
    if "areas" in data:
        before = len(errors)
        _check_table(data["areas"], AREA_KEYS, "areas", errors)
        areas = data["areas"]
        if len(errors) == before and areas["accepted"] > areas["set_up"]:
            errors.append(f"areas: accepted ({areas['accepted']}) is more than set_up ({areas['set_up']})")

    if "comment" in data and not isinstance(data["comment"], str):
        errors.append("comment must be a string")

    if errors:
        raise MetricsSnapshotError("; ".join(errors))

    warnings = []
    if months_ok:
        series = data["datasets_monthly"]
        for before, after in zip(series, series[1:]):
            if after["count"] < before["count"]:
                warnings.append(
                    f"datasets_monthly falls from {before['count']} to {after['count']} in {after['date']} "
                    "(metrics cache not cleared before the fetch?)"
                )
        if series[-1]["count"] != data["counts"]["datasets"]:
            warnings.append(
                f"datasets_monthly ends at {series[-1]['count']}, counts.datasets is {data['counts']['datasets']}"
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
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
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
