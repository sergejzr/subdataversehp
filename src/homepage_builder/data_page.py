"""Data page (/at/data/): public key figures of the repository.

Rendered by landing.render_data_page() after the landing, on dev and test
only (landing.DATA_ENVIRONMENTS). Two views, each rendered on its own:

  snapshot  /at/data/, /at/en/data/                 metrics.json, fetched by hand
            /at/data/<alias>/, /at/en/data/<alias>/ with scripts/fetch_metrics.py
  sample    /at/data/beispiel/, /at/en/data/sample/ metrics.sample.json, made-up
                                                    numbers: how the page may look later

The snapshot view has one page for the whole repository and one per area:
the participating universities and the demo area, with their sub-areas.
A menu lists the top level only, so it stays short however many sub-areas
there are; each area page shows its own sub-areas as a tree. The overview
names no university with its numbers: there is no table to compare them.

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
VIEWS = {"snapshot": "metrics.json", "sample": "metrics.sample.json"}
SAMPLE_PATH = {"de": "beispiel", "en": "sample"}
# Numbers and curl examples come from this host only, so a test page never
# shows another system's numbers.
ALLOWED_SERVERS = {"https://datapublication-nrw-test.hrz.uni-bonn.de"}
DEMO_LABEL = "demo"
# Area in the examples of the overview: the demo area stays on test for good
# (FS4) and singles out no university. Area pages use their own alias.
EXAMPLE_LABEL = DEMO_LABEL
# Seed collections (tooling/seed) get no page and no place in the tree; their
# datasets still count in every number above them.
HIDDEN_PREFIXES = ("zz-test-",)
# Test leftovers on the test system (2026-11-24), hidden the same way.
HIDDEN_ALIASES = {"TestDV", "agrarwirtschaft-hsbi", "testverse"}
_ALIAS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
TOP_SUBJECTS = 8
OTHER_SUBJECT = "Other"  # Dataverse's catch-all subject, always under "Weitere"
UNCATEGORIZED = "Uncategorized"  # Dataverse's collection category without a choice, listed last
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


# ---------- Formatting ----------

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


def plural(n: int, one: str, many: str, d: dict) -> str:
    return (one if n == 1 else many).format(n=number(n, d))


def inline(text: str) -> Markup:
    """Escaped text in which `backticks` become <code>."""
    return Markup(_CODE_SPAN.sub(r"<code>\1</code>", str(Markup.escape(text))))


def month_label(month: str, d: dict) -> str:
    year, month_number = month.split("-")
    return f"{d['months'][int(month_number) - 1]} {year}"


# ---------- Charts ----------

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
        rows.append({
            "label": d["type_groups"][name],
            "count": group["count"],
            "count_text": number(group["count"], d),
            "size_text": size(group["size"], d),
            "value": f"{plural(group['count'], t['files_one'], t['files_many'], d)} · {size(group['size'], d)}",
            "types": ", ".join(sorted(group["types"])),
            "rest": name == "other",
        })
    return rows


def category_rows(items: list[dict], d: dict) -> tuple[list[dict], list[str]]:
    """Collection categories by count, "Uncategorized" last; (rows, unknown categories)."""
    names = d["categories"]
    unknown = sorted({item["category"] for item in items} - set(names))
    ordered = sorted(
        items, key=lambda item: (item["category"] == UNCATEGORIZED, -item["count"], item["category"])
    )
    rows = [
        {
            "label": names.get(item["category"], item["category"]),
            "count": item["count"],
            "value": number(item["count"], d),
            "rest": item["category"] == UNCATEGORIZED,
        }
        for item in ordered
    ]
    return rows, unknown


# ---------- Areas ----------

def visible_areas(tree: dict, partner_labels: list[str]) -> tuple[dict[str, dict], list[str], list[str]]:
    """Areas that get a page: the participating universities and the demo area
    at the top, their sub-areas below; seed collections, test leftovers and
    everything below them left out. Returns (areas by alias, top-level aliases, warnings)."""
    wanted = set(partner_labels) | {DEMO_LABEL}
    reserved = set(SAMPLE_PATH.values())
    areas: dict[str, dict] = {}
    top: list[str] = []
    warnings: list[str] = []

    def size(node: dict) -> int:
        return 1 + sum(size(child) for child in node.get("children", []))

    def add(node: dict, parent: str | None) -> None:
        alias = node["alias"]
        hidden = alias.startswith(HIDDEN_PREFIXES) or alias in HIDDEN_ALIASES
        if not hidden and (alias in reserved or not _ALIAS.match(alias)):
            warnings.append(f"collection {alias!r} gets no page: the alias cannot be a path below /at/data/")
            hidden = True
        if hidden:
            # Still counted in the numbers above: the page says how many are left out.
            if parent:
                areas[parent]["hidden"] += size(node)
            return
        areas[alias] = {
            "alias": alias, "dv_name": node["name"].strip() or alias, "parent": parent, "children": [], "hidden": 0,
        }
        if parent:
            areas[parent]["children"].append(alias)
        for child in node.get("children", []):
            add(child, alias)

    for node in tree.get("children", []):
        if node["alias"] in wanted:
            top.append(node["alias"])
            add(node, None)
    return areas, top, warnings


def area_name(area: dict, s: dict) -> str:
    """Our names for the top level (strings [names]), Dataverse's below."""
    if area["parent"] is None:
        if area["alias"] == DEMO_LABEL:
            return s["data"]["nav"]["demo_name"]
        return s["names"].get(area["alias"], area["dv_name"])
    return area["dv_name"]


def page_url(lang: str, alias: str | None = None, sample: bool = False) -> str:
    lang_part = "" if lang == landing.DEFAULT_LANGUAGE else f"{lang}/"
    url = f"{landing.LANDING_BASE_PATH}{lang_part}{SLUG}/"
    if sample:
        url += f"{SAMPLE_PATH[lang]}/"
    elif alias:
        url += f"{alias}/"
    return url


# ---------- Page ----------

def page_context(
    lang: str,
    data: dict,
    strings: dict,
    *,
    view: str,
    alias: str | None,
    areas: dict,
    top: list[str],
    with_switch: bool,
) -> dict:
    s = strings[lang]
    d = s["data"]
    root_alias = data["tree"]["alias"]
    block = data["collections"][alias or root_alias]
    counts = block["counts"]
    fetched = datetime.fromisoformat(data["fetched_at"])
    suffix = f" ({d['sample_suffix']})" if view == "sample" else ""
    area = areas.get(alias) if alias else None
    name = area_name(area, s) if area else None

    def sort_key(a: str) -> tuple:
        return (a == DEMO_LABEL, landing._sort_key(area_name(areas[a], s)))

    # Menu (top level only) and path, snapshot view only.
    menu = None
    breadcrumb = None
    if view == "snapshot":
        ancestors = []
        node = area
        while node:
            ancestors.insert(0, node["alias"])
            node = areas.get(node["parent"]) if node["parent"] else None
        menu = [{"label": d["nav"]["all_areas"], "href": page_url(lang), "current": "page" if not alias else None}]
        for a in sorted(top, key=sort_key):
            current = "page" if a == alias else ("true" if ancestors and ancestors[0] == a else None)
            menu.append({"label": area_name(areas[a], s), "href": page_url(lang, a), "current": current})
        if area:
            breadcrumb = [{"label": d["nav"]["all_areas"], "href": page_url(lang)}]
            breadcrumb += [{"label": area_name(areas[a], s), "href": page_url(lang, a)} for a in ancestors[:-1]]
            breadcrumb.append({"label": name, "href": None})
    switch = None
    if with_switch and not alias:
        switch = [
            {"label": d["switch_snapshot"], "href": page_url(lang), "current": view == "snapshot"},
            {"label": d["switch_sample"], "href": page_url(lang, sample=True), "current": view == "sample"},
        ]

    def subtree(aliases: list[str]) -> list[dict]:
        nodes = []
        for a in sorted(aliases, key=lambda a: landing._sort_key(area_name(areas[a], s))):
            n = data["collections"][a]["counts"]["datasets"]
            nodes.append({
                "label": area_name(areas[a], s),
                "href": page_url(lang, a),
                "value": plural(n, d["tree"]["datasets_one"], d["tree"]["datasets_many"], d),
                "children": subtree(areas[a]["children"]),
            })
        return nodes

    # Monthly series
    months = block["datasets_monthly"]
    monthly = None
    if months:
        first, last = months[0], months[-1]
        steps = [{"datum": date(*map(int, item["date"].split("-")), 1), "n": item["count"]} for item in months]
        until = max(fetched.date(), steps[-1]["datum"])
        y_max = max(max(item["count"] for item in months), 1)
        first_month, end_month = month_label(first["date"], d), month_label(f"{until:%Y-%m}", d)
        if len(months) == 1:
            description = d["monthly"]["desc_single"].format(
                last=number(last["count"], d), last_month=month_label(last["date"], d)
            )
        else:
            description = d["monthly"]["desc"].format(
                first=number(first["count"], d),
                first_month=first_month,
                last=number(last["count"], d),
                last_month=month_label(last["date"], d),
            )
        monthly = {
            "chart": landing.step_chart_svg(
                steps,
                y_max,
                until,
                s["date_format"],
                d["monthly"]["caption"] + suffix,
                axis_labels=(first_month, end_month),
                description=description,
                chart_id=CHART_ID,
            ),
            "rows": [{"label": month_label(item["date"], d), "count": number(item["count"], d)} for item in months],
        }

    subject_bars, subject_table, unknown_subjects = subject_rows(block["datasets_by_subject"], d)
    categories, unknown_categories = category_rows(block["dataverses_by_category"], d)
    total_size = sum(item["size"] for item in block["files_by_type"])
    unique = sum(item["count"] for item in block["unique_downloads"])
    t = d["tiles"]
    tiles = [
        {
            "value": number(counts["datasets"], d),
            "label": t["datasets"],
            "sub": t["datasets_recent"].format(n=number(counts["datasets_past_30"], d)) if counts["datasets"] else None,
        },
        {"value": number(counts["files"], d), "label": t["files"], "sub": None},
        {"value": size(total_size, d), "label": t["volume"], "sub": None},
        {"value": number(unique, d), "label": t["downloads"], "sub": None},
        {"value": number(counts["dataverses"], d), "label": t["sub_areas"] if alias else t["areas"], "sub": None},
    ]

    server = data["server"]
    example = alias or EXAMPLE_LABEL
    api = f"{server}/api/info/metrics"
    query = f'?parentAlias={example}"'
    curl = [
        f'curl "{api}/datasets',
        f'curl "{api}/datasets/monthly',
        # Continued with a backslash, so no line is longer than the others.
        f'curl -H "Accept: application/json" \\\n  "{api}/files/byType',
    ]
    a = d["access"]
    browse_label = a["browse_this"] if alias else a["browse_example"]
    browse_link = Markup('<a href="{}">{}</a>').format(f"{server}/dataverse/{example}", browse_label)
    api_text = a["api_text_area"].replace("{alias}", example) if alias else a["api_text"]

    notice = d["notice"]
    title = name or d["title"]
    return {
        "view": view,
        "suffix": suffix,
        "title": title,
        "page_title": f"{name} · {d['title']}" if name else d["title"],
        "lead": d["area_lead"].format(name=name) if name else d["lead"],
        "menu": menu,
        "breadcrumb": breadcrumb,
        "switch": switch,
        "notice_title": notice[f"{view}_title"],
        "notice_text": notice[f"{view}_text"].format(date=fetched.strftime(s["date_format"])),
        "tiles": tiles,
        "empty": counts["datasets"] == 0,
        "monthly": monthly,
        "subjects": {"bars": with_bars(subject_bars), "table": subject_table} if subject_bars else None,
        "types": with_bars(type_rows(block["files_by_type"], d)) or None,
        "subtree": subtree(area["children"]) if area and area["children"] else None,
        "hidden_note": (
            plural(area["hidden"], d["tree"]["hidden_one"], d["tree"]["hidden_many"], d)
            if area and area["hidden"] else None
        ),
        "categories": with_bars(categories) or None,
        "access": {
            "browse": inline(a["browse_text"]).replace("{example}", browse_link),
            "api": inline(api_text),
            # The query is one unit (span.q, nowrap from 700 px in data.css), so a
            # long command breaks before it, not inside the alias. Copying gives
            # the commands unchanged.
            "curl": Markup("\n\n").join(
                Markup('{}<wbr><span class="q">{}</span>').format(line, query) for line in curl
            ),
            "formats": inline(a["formats"]),
        },
        "missing": [inline(item) for item in d["missing"]["items"]],
        "unknown": [f"subject {x!r}" for x in unknown_subjects] + [f"category {x!r}" for x in unknown_categories],
    }


def load_view(view: str, landing_dir: Path) -> tuple[dict, list[str]]:
    filename = VIEWS[view]
    try:
        data, warnings = metrics_snapshot.load(landing_dir / filename, view)
    except metrics_snapshot.MetricsSnapshotError as exc:
        raise DataPageError(str(exc)) from None
    if data["server"] not in ALLOWED_SERVERS:
        raise DataPageError(f"{filename}: server {data['server']} is not one of {', '.join(sorted(ALLOWED_SERVERS))}")
    return data, [f"{filename}: {warning}" for warning in warnings]


def render(
    landing_dir: Path,
    *,
    env,
    strings: dict,
    landing_urls: dict,
    css_href: str,
    css_files: dict,
    legal_urls: dict,
    partner_labels: list[str],
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

    loaded: dict[str, tuple[dict, dict, list[str]]] = {}
    for view in VIEWS:
        try:
            data, warnings = load_view(view, landing_dir)
        except DataPageError as exc:
            log.append((True, f"ERROR: data page {view} skipped: {exc}"))
            continue
        log += [(True, f"Warning: data page {view}: {warning}") for warning in warnings]
        if view == "snapshot":
            areas, top, area_warnings = visible_areas(data["tree"], partner_labels)
            log += [(True, f"Warning: data page {view}: {warning}") for warning in area_warnings]
        else:
            areas, top = {}, []
        loaded[view] = (data, areas, top)

    def render_page(view: str, lang: str, alias: str | None, with_switch: bool) -> tuple[str, str, int]:
        data, areas, top = loaded[view]
        s = strings[lang]
        url = page_url(lang, alias, sample=view == "sample")
        context = page_context(
            lang, data, strings, view=view, alias=alias, areas=areas, top=top, with_switch=with_switch
        )
        if lang == landing.DEFAULT_LANGUAGE:
            for item in context.pop("unknown"):
                log.append((True, f"Warning: data page {view}: no German name for {item}"))
        else:
            context.pop("unknown")
        other = s["lang_switch_lang"]
        html = template.render(
            lang=lang,
            s=s,
            d=s["data"],
            urls=landing_urls,
            default_lang=landing.DEFAULT_LANGUAGE,
            css_href=css_href,
            data_css_href=data_css_href,
            alt_url=page_url(other, alias, sample=view == "sample"),
            legal_urls=legal_urls,
            page={"title": context["page_title"]},
            **context,
        )
        violations, loaded_paths = landing.check_page(html, url, all_css)
        if violations:
            raise DataPageError(f"{url} breaks the landing's claims: " + "; ".join(violations))
        weight = landing.page_weight(html, loaded_paths, landing_dir, {css_path: css_source})[0]
        if weight >= landing_weights[lang]:
            raise DataPageError(f"{url} weighs {weight} B, not less than the landing ({landing_weights[lang]} B)")
        return url, html, weight

    # Render with the view switch while both views render; drop a failing
    # view and render the rest again, so no link points to a gap.
    while loaded:
        pages: dict[str, str] = {}
        weights: list[int] = []
        failed = None
        for view in list(loaded):
            aliases = [None] + (list(loaded[view][1]) if view == "snapshot" else [])
            try:
                for alias in aliases:
                    for lang in landing.LANGUAGES:
                        url, html, weight = render_page(view, lang, alias, with_switch=len(loaded) > 1)
                        pages[url.removeprefix(base) + "index.html"] = html
                        weights.append(weight)
            except Exception as exc:
                failed = view
                log.append((True, f"ERROR: data page {view} skipped: {type(exc).__name__}: {exc}"))
                break
        if failed is None:
            pages[f"{SLUG}/{CSS_FILE}"] = css_text
            log.append((
                False,
                f"Data page written: {', '.join(loaded)}, {len(weights)} pages, "
                f"{min(weights)}..{max(weights)} B each",
            ))
            return pages, list(dict.fromkeys(log))
        del loaded[failed]
    return {}, list(dict.fromkeys(log))
