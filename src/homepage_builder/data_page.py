"""Data page (/at/data/): public key figures of the repository.

Rendered by landing.render_data_page() after the landing, on dev and test
only (landing.DATA_ENVIRONMENTS). Two views, each rendered on its own:

  snapshot  /at/data/, /at/en/data/                 metrics.json, fetched by hand
                                                    with scripts/fetch_metrics.py
  sample    /at/data/beispiel/, /at/en/data/sample/ metrics.sample.json, made-up
                                                    numbers: how the page may look later

A missing or broken file skips its view, never the landing. The views link to
each other only when both render. The pages follow the landing's claims and
are checked the same way: no JavaScript, no third-party requests, and each
page lighter than the landing in the same language.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from pathlib import Path

from markupsafe import Markup

try:
    from . import landing, metrics_snapshot
except ImportError:
    import landing
    import metrics_snapshot

SLUG = "data"
TEMPLATE = "data-jinja.html"
CSS_FILE = "data.css"
# view -> (file in templates/landing/, path below data/ per language)
VIEWS = {
    "snapshot": ("metrics.json", {"de": "", "en": ""}),
    "sample": ("metrics.sample.json", {"de": "beispiel/", "en": "sample/"}),
}
# Numbers and curl examples come from this host only, so a test page never
# shows another system's numbers.
ALLOWED_SERVERS = {"https://datapublication-nrw-test.hrz.uni-bonn.de"}
# Area in the examples: the demo area stays on test for good (FS4) and singles
# out no university.
EXAMPLE_LABEL = "demo"
TOP_SUBJECTS = 8
OTHER_SUBJECT = "Other"  # Dataverse's catch-all subject, always under "Weitere"
CHART_ID = "chart-monthly"

TYPE_GROUPS = ("tables", "code", "images", "text", "other")
_TABLE_TYPES = {
    "text/csv",
    "text/tab-separated-values",
    "text/tsv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/x-rlang-transport",
}
_TABLE_PREFIXES = ("application/x-stata", "application/x-spss")
_TEXT_TYPES = {
    "text/plain",
    "text/markdown",
    "text/x-markdown",
    "text/html",
    "text/rtf",
    "application/rtf",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
    "text/x-tex",
    "application/x-tex",
}
_CODE_TYPES = {"application/x-ipynb+json", "application/x-sh", "application/x-shellscript", "text/javascript"}
# Dataverse files scripts as text/x-python, type/x-r-syntax, text/x-stata-syntax ...
_CODE_PREFIXES = ("text/x-", "type/x-")
_CODE_SPAN = re.compile(r"`([^`]+)`")


class DataPageError(ValueError):
    """A view cannot be rendered."""


def type_group(contenttype: str) -> str:
    """Group of a MIME type for the file chart; anything unknown is "other"."""
    mime = contenttype.split(";", 1)[0].strip().lower()
    if mime in _TABLE_TYPES or mime.startswith(_TABLE_PREFIXES):
        return "tables"
    if mime.startswith("image/"):
        return "images"
    if mime in _TEXT_TYPES:
        return "text"
    if mime in _CODE_TYPES or mime.startswith(_CODE_PREFIXES):
        return "code"
    return "other"


def number(value: int, d: dict) -> str:
    return f"{value:,}".replace(",", d["thousands_separator"])


def size(value: int, d: dict) -> str:
    """Bytes in SI units with one decimal: 22274450 -> "22,3 MB" (de)."""
    units = ("B", "kB", "MB", "GB", "TB", "PB")
    amount, unit = float(value), 0
    while round(amount, 1) >= 1000 and unit < len(units) - 1:
        amount /= 1000
        unit += 1
    text = f"{int(amount):,}" if unit == 0 else f"{amount:,.1f}"
    text = text.replace(",", "\0").replace(".", d["decimal_separator"]).replace("\0", d["thousands_separator"])
    return f"{text} {units[unit]}"


def inline(text: str) -> Markup:
    """Escaped text in which `backticks` become <code>."""
    return Markup(_CODE_SPAN.sub(r"<code>\1</code>", str(Markup.escape(text))))


def month_label(month: str, d: dict) -> str:
    year, number_ = month.split("-")
    return f"{d['months'][int(number_) - 1]} {year}"


def with_bars(rows: list[dict]) -> list[dict]:
    """Bar length in percent of the largest row (viewBox width 100)."""
    top = max((row["count"] for row in rows), default=0)
    return [{**row, "pct": f"{row['count'] / top * 100:.2f}" if top else "0"} for row in rows]


def subject_rows(items: list[dict], d: dict) -> tuple[list[dict], list[dict], list[str]]:
    """(bars, table, unknown subjects): the largest TOP_SUBJECTS, the rest and
    "Other" as one bar "Weitere"; the table lists every subject."""
    names = d["subjects"]
    unknown = sorted({item["subject"] for item in items} - set(names))

    def label(subject: str) -> str:
        return names.get(subject, subject)

    ordered = sorted(
        (item for item in items if item["subject"] != OTHER_SUBJECT),
        key=lambda item: (-item["count"], label(item["subject"]).casefold()),
    )
    other = [item for item in items if item["subject"] == OTHER_SUBJECT]
    # A single leftover subject is shown as itself, not as "Weitere".
    if len(ordered) > TOP_SUBJECTS + 1:
        shown, rest = ordered[:TOP_SUBJECTS], ordered[TOP_SUBJECTS:] + other
    else:
        shown, rest = ordered, other
    bars = [{"label": label(item["subject"]), "count": item["count"], "rest": False} for item in shown]
    if rest:
        bars.append({"label": d["subjects_chart"]["rest"], "count": sum(item["count"] for item in rest), "rest": True})
    for row in bars:
        row["value"] = number(row["count"], d)
    table = [{"label": label(item["subject"]), "value": number(item["count"], d)} for item in ordered + other]
    return bars, table, unknown


def type_rows(items: list[dict], d: dict) -> list[dict]:
    """File groups by count, "other" last; empty groups left out."""
    groups = {group: {"count": 0, "size": 0, "types": []} for group in TYPE_GROUPS}
    for item in items:
        group = groups[type_group(item["contenttype"])]
        group["count"] += item["count"]
        group["size"] += item["size"]
        group["types"].append(item["contenttype"])
    present = [name for name in TYPE_GROUPS if groups[name]["count"]]
    present.sort(key=lambda name: (name == "other", -groups[name]["count"], TYPE_GROUPS.index(name)))
    t = d["types"]
    rows = []
    for name in present:
        group = groups[name]
        files = (t["files_one"] if group["count"] == 1 else t["files_many"]).format(n=number(group["count"], d))
        rows.append({
            "label": d["type_groups"][name],
            "count": group["count"],
            "count_text": number(group["count"], d),
            "size_text": size(group["size"], d),
            "value": f"{files} · {size(group['size'], d)}",
            "types": ", ".join(sorted(group["types"])),
            "rest": name == "other",
        })
    return rows


def page_url(view: str, lang: str) -> str:
    lang_part = "" if lang == landing.DEFAULT_LANGUAGE else f"{lang}/"
    return f"{landing.LANDING_BASE_PATH}{lang_part}{SLUG}/{VIEWS[view][1][lang]}"


def load_view(view: str, landing_dir: Path, areas: dict) -> tuple[dict, list[str]]:
    """Validated data of one view, with the areas it shows."""
    filename = VIEWS[view][0]
    try:
        data, warnings = metrics_snapshot.load(landing_dir / filename, view)
    except metrics_snapshot.MetricsSnapshotError as exc:
        raise DataPageError(str(exc)) from None
    if data["server"] not in ALLOWED_SERVERS:
        raise DataPageError(f"{filename}: server {data['server']} is not one of {', '.join(sorted(ALLOWED_SERVERS))}")
    if view == "snapshot":
        data = {**data, "areas": areas}
    return data, [f"{filename}: {warning}" for warning in warnings]


def page_context(view: str, lang: str, data: dict, strings: dict, switch_views: list[str]) -> dict:
    s = strings[lang]
    d = s["data"]
    fetched = datetime.fromisoformat(data["fetched_at"])
    suffix = f" ({d['sample_suffix']})" if view == "sample" else ""
    notice = d["notice"]

    months = data["datasets_monthly"]
    first, last = months[0], months[-1]
    steps = [{"datum": date(*map(int, item["date"].split("-")), 1), "n": item["count"]} for item in months]
    until = max(fetched.date(), steps[-1]["datum"])
    y_max = max(max(item["count"] for item in months), 1)
    first_month, last_month = month_label(first["date"], d), month_label(f"{until:%Y-%m}", d)
    if len(months) == 1:
        description = d["monthly"]["desc_single"].format(last=number(last["count"], d), last_month=last_month)
    else:
        description = d["monthly"]["desc"].format(
            first=number(first["count"], d),
            first_month=first_month,
            last=number(last["count"], d),
            last_month=month_label(last["date"], d),
        )
    chart = landing.step_chart_svg(
        steps,
        y_max,
        until,
        s["date_format"],
        d["monthly"]["caption"] + suffix,
        axis_labels=(first_month, last_month),
        description=description,
        chart_id=CHART_ID,
    )

    subject_bars, subject_table, unknown = subject_rows(data["datasets_by_subject"], d)
    types = type_rows(data["files_by_type"], d)
    areas = data["areas"]
    total_size = sum(item["size"] for item in data["files_by_type"])
    unique = sum(item["count"] for item in data["unique_downloads"])
    tiles = [
        {"value": number(data["counts"]["datasets"], d), "label": d["tiles"]["datasets"], "sub": None},
        {"value": number(data["counts"]["files"], d), "label": d["tiles"]["files"], "sub": None},
        {"value": size(total_size, d), "label": d["tiles"]["volume"], "sub": None},
        {"value": number(unique, d), "label": d["tiles"]["downloads"], "sub": None},
        {
            "value": number(areas["set_up"], d),
            "label": d["tiles"]["areas"],
            "sub": d["tiles"]["areas_accepted"].format(n=number(areas["accepted"], d)),
        },
    ]

    server = data["server"]
    api = f"{server}/api/info/metrics"
    curl = [
        f'curl "{api}/datasets?parentAlias={EXAMPLE_LABEL}"',
        f'curl "{api}/datasets/monthly?parentAlias={EXAMPLE_LABEL}"',
        f'curl -H "Accept: application/json" "{api}/files/byType?parentAlias={EXAMPLE_LABEL}"',
    ]
    a = d["access"]
    example_link = Markup('<a href="{}">{}</a>').format(f"{server}/dataverse/{EXAMPLE_LABEL}", a["browse_example"])

    switch = None
    if len(switch_views) > 1:
        switch = [
            {"label": d[f"switch_{other}"], "href": page_url(other, lang), "current": other == view}
            for other in switch_views
        ]
    return {
        "view": view,
        "suffix": suffix,
        "switch": switch,
        "notice_title": notice[f"{view}_title"],
        "notice_text": notice[f"{view}_text"].format(date=fetched.strftime(s["date_format"])),
        "tiles": tiles,
        "monthly": {
            "chart": chart,
            "rows": [{"label": month_label(item["date"], d), "count": number(item["count"], d)} for item in months],
        },
        "subjects": {"bars": with_bars(subject_bars), "table": subject_table, "unknown": unknown},
        "types": with_bars(types),
        "access": {
            "browse": inline(a["browse_text"]).replace("{example}", example_link),
            "api": inline(a["api_text"]),
            "curl": "\n\n".join(curl),
            "formats": inline(a["formats"]),
        },
        "missing": [inline(item) for item in d["missing"]["items"]],
    }


def render(
    landing_dir: Path,
    *,
    env,
    strings: dict,
    landing_urls: dict,
    css_href: str,
    css_files: dict,
    legal_urls: dict,
    areas: dict,
    landing_weights: dict,
) -> tuple[dict[str, str], list[tuple[bool, str]]]:
    """Files to write below the landing's output folder, and log lines (is_error, text)."""
    log: list[tuple[bool, str]] = []
    base = landing.LANDING_BASE_PATH
    css_path = f"{base}{SLUG}/{CSS_FILE}"
    css_source = landing_dir / CSS_FILE
    css_text = css_source.read_text(encoding="utf-8")
    data_css_href = f"{css_path}?v={hashlib.sha256(css_text.encode('utf-8')).hexdigest()[:8]}"
    all_css = {**css_files, css_path: css_text}
    template = env.get_template(TEMPLATE)

    loaded = {}
    for view in VIEWS:
        try:
            loaded[view], warnings = load_view(view, landing_dir, areas)
        except DataPageError as exc:
            log.append((True, f"ERROR: data page {view} skipped: {exc}"))
            continue
        log += [(True, f"Warning: data page {view}: {warning}") for warning in warnings]

    # Render with the view switch while every remaining view renders; drop a
    # failing view and render the rest again, so no switch points to a gap.
    while loaded:
        views = list(loaded)
        pages: dict[str, str] = {}
        weights: list[str] = []
        failed = None
        for view in views:
            try:
                for lang in landing.LANGUAGES:
                    url = page_url(view, lang)
                    context = page_context(view, lang, loaded[view], strings, views)
                    if lang == landing.DEFAULT_LANGUAGE:
                        for subject in context["subjects"]["unknown"]:
                            log.append((True, f"Warning: data page {view}: no German name for subject {subject!r}"))
                    html = template.render(
                        lang=lang,
                        s=strings[lang],
                        d=strings[lang]["data"],
                        urls=landing_urls,
                        default_lang=landing.DEFAULT_LANGUAGE,
                        css_href=css_href,
                        data_css_href=data_css_href,
                        alt_url=page_url(view, strings[lang]["lang_switch_lang"]),
                        legal_urls=legal_urls,
                        page={"title": strings[lang]["data"]["title"]},
                        **context,
                    )
                    violations, loaded_paths = landing.check_page(html, url, all_css)
                    if violations:
                        raise DataPageError(f"{lang} page breaks the landing's claims: " + "; ".join(violations))
                    weight = landing.page_weight(html, loaded_paths, landing_dir, {css_path: css_source})[0]
                    if weight >= landing_weights[lang]:
                        raise DataPageError(
                            f"{lang} page weighs {weight} B, not less than the landing ({landing_weights[lang]} B)"
                        )
                    pages[url.removeprefix(base) + "index.html"] = html
                    weights.append(f"{url} {weight} B")
            except Exception as exc:
                failed = view
                log.append((True, f"ERROR: data page {view} skipped: {type(exc).__name__}: {exc}"))
                break
        if failed is None:
            pages[f"{SLUG}/{CSS_FILE}"] = css_text
            log.append((False, f"Data page written: {', '.join(weights)}"))
            return pages, list(dict.fromkeys(log))
        del loaded[failed]
    return {}, list(dict.fromkeys(log))
