"""Render the new consortium landing page (hidden preview, one page per language).

Inputs live in templates/landing/:
  landing-jinja.html   the page template, rendered once per language
  landing.css          copied next to the rendered pages
  strings.<lang>.toml  all visible text
  news.toml            [[news]] entries
  status.csv           append-only log: label,status,datum

The caller wraps render_landing() so that bad landing data only skips the
preview; nothing is written unless both languages render.
"""
from __future__ import annotations

import csv
import re
import shutil
import tomllib
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup

# Public URL of the landing page. Output goes to the same path below at/.
# At go-live this becomes "/at/".
LANDING_BASE_PATH = "/at/_vorschau/"

LANGUAGES = ("de", "en")
DEFAULT_LANGUAGE = "de"
STATUSES = ("eingerichtet", "abgenommen", "live")
NO_STATUS = "none"
EXTERNAL = "external"  # partner runs its own repository (unis.csv repourl)
STATUS_HEADER = ["label", "status", "datum"]
NEWS_KEYS_REQUIRED = {"datum", "titel_de", "titel_en"}
NEWS_KEYS_OPTIONAL = {"text_de", "text_en", "link"}

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RECT_LABEL = re.compile(r'inkscape:label="rect_([a-z0-9-]+)"')
_TEXT_LABEL = re.compile(r'inkscape:label="text_([a-z0-9-]+)"')


class LandingDataError(ValueError):
    pass


def _parse_iso_date(value) -> date:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not _ISO_DATE.match(value.strip()):
        raise ValueError(f"not an ISO date (YYYY-MM-DD): {value!r}")
    return date.fromisoformat(value.strip())


def partner_labels(svg_text: str) -> list[str]:
    """Partner labels in map order: every rect_<label> box and text_<label>.

    Taking both means a partner missing its box (or its label) still counts,
    so map_with_status() notices the gap instead of silently shrinking the set.
    """
    labels = list(dict.fromkeys(_RECT_LABEL.findall(svg_text) + _TEXT_LABEL.findall(svg_text)))
    if not labels:
        raise LandingDataError("map SVG contains no rect_<label> partner boxes")
    return labels


def read_status_log(path: Path, partners: list[str], external: set[str]) -> list[dict]:
    errors = []
    rows = []
    last_date: dict[str, date] = {}

    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if [h.strip() for h in header or []] != STATUS_HEADER:
            raise LandingDataError(f"{path.name}: header must be {','.join(STATUS_HEADER)}, got {header!r}")

        for record in reader:
            line = reader.line_num
            if not any(field.strip() for field in record):
                continue
            if len(record) != len(STATUS_HEADER):
                errors.append(f"line {line}: expected {len(STATUS_HEADER)} fields, got {len(record)}")
                continue
            label, status, datum = (field.strip() for field in record)

            if label not in partners:
                errors.append(f"line {line}: unknown label {label!r}")
            elif label in external:
                errors.append(f"line {line}: {label!r} has its own repository (repourl) and takes no status rows")
            if status not in STATUSES:
                errors.append(f"line {line}: unknown status {status!r} (allowed: {', '.join(STATUSES)})")
            try:
                day = _parse_iso_date(datum)
            except ValueError as exc:
                errors.append(f"line {line}: {exc}")
                continue

            if label in last_date and day < last_date[label]:
                errors.append(f"line {line}: date {day} for {label!r} is before its previous entry {last_date[label]}")
            last_date[label] = day
            rows.append({"label": label, "status": status, "datum": day})

    if errors:
        raise LandingDataError(f"{path.name}: " + "; ".join(errors))
    return rows


def read_news(path: Path) -> list[dict]:
    with path.open("rb") as fh:
        data = tomllib.load(fh)

    entries = data.get("news", [])
    if not isinstance(entries, list):
        raise LandingDataError(f"{path.name}: 'news' must be an array of tables ([[news]])")

    errors = []
    news = []
    for i, entry in enumerate(entries, start=1):
        keys = set(entry)
        missing = NEWS_KEYS_REQUIRED - keys
        unknown = keys - NEWS_KEYS_REQUIRED - NEWS_KEYS_OPTIONAL
        if missing:
            errors.append(f"entry {i}: missing {', '.join(sorted(missing))}")
        if unknown:
            errors.append(f"entry {i}: unknown keys {', '.join(sorted(unknown))}")
        if missing:
            continue
        try:
            day = _parse_iso_date(entry["datum"])
        except ValueError as exc:
            errors.append(f"entry {i}: {exc}")
            continue
        news.append({**entry, "datum": day})

    if errors:
        raise LandingDataError(f"{path.name}: " + "; ".join(errors))
    return sorted(news, key=lambda n: n["datum"], reverse=True)


def _key_paths(table: dict, prefix: str = "") -> set[str]:
    paths = set()
    for key, value in table.items():
        path = f"{prefix}{key}"
        paths.add(path)
        if isinstance(value, dict):
            paths |= _key_paths(value, f"{path}.")
    return paths


def read_strings(landing_dir: Path) -> dict[str, dict]:
    strings = {}
    for lang in LANGUAGES:
        with (landing_dir / f"strings.{lang}.toml").open("rb") as fh:
            strings[lang] = tomllib.load(fh)

    reference = _key_paths(strings[DEFAULT_LANGUAGE])
    for lang in LANGUAGES:
        diff = reference ^ _key_paths(strings[lang])
        if diff:
            raise LandingDataError(
                f"strings.{lang}.toml and strings.{DEFAULT_LANGUAGE}.toml differ in keys: {', '.join(sorted(diff))}"
            )
    return strings


def progress_steps(rows: list[dict]) -> list[dict]:
    """Cumulative number of partners with any status, one step per date."""
    first_seen: dict[str, date] = {}
    for row in rows:
        first_seen.setdefault(row["label"], row["datum"])

    steps = []
    count = 0
    for day in sorted(set(first_seen.values())):
        count += sum(1 for d in first_seen.values() if d == day)
        steps.append({"datum": day, "n": count})
    return steps


def step_chart_svg(steps: list[dict], total: int, until: date, fmt: str, title: str) -> Markup:
    """Minimal step chart; the template shows the same data as a table."""
    if not steps:
        return Markup("")

    width, height = 600, 220
    left, right, top, bottom = 40, 20, 15, 30
    start = steps[0]["datum"]
    span = max((until - start).days, 1)

    def x(day: date) -> float:
        return left + (day - start).days / span * (width - left - right)

    def y(n: int) -> float:
        return top + (1 - n / total) * (height - top - bottom)

    path = [f"M{x(start):.1f},{y(0):.1f}"]
    for step in steps:
        path.append(f"H{x(step['datum']):.1f}V{y(step['n']):.1f}")
    path.append(f"H{x(max(until, steps[-1]['datum'])):.1f}")

    base = height - bottom
    parts = [
        f'<svg class="step-chart" viewBox="0 0 {width} {height}" role="img" aria-label="{Markup.escape(title)}">',
        f'<line x1="{left}" y1="{base}" x2="{width - right}" y2="{base}" stroke="currentColor"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{base}" stroke="currentColor"/>',
        f'<text x="{left - 6}" y="{y(0):.1f}" text-anchor="end" dominant-baseline="middle">0</text>',
        f'<text x="{left - 6}" y="{y(total):.1f}" text-anchor="end" dominant-baseline="middle">{total}</text>',
        f'<text x="{left}" y="{height - 8}">{start.strftime(fmt)}</text>',
        f'<text x="{width - right}" y="{height - 8}" text-anchor="end">{until.strftime(fmt)}</text>',
        f'<path d="{"".join(path)}" fill="none" stroke="currentColor" stroke-width="3"/>',
        "</svg>",
    ]
    return Markup("".join(parts))


def partner_href(label: str, status: str, repourl: str) -> str | None:
    """One link rule for map and list."""
    if status == EXTERNAL:
        return repourl
    if status == "live":
        return f"/at/{label}/"
    return None


def _check_all_marked(what: str, marked: list[str], partners: list[str]) -> None:
    missing = [label for label in partners if label not in marked]
    if len(marked) != len(partners) or missing:
        raise LandingDataError(
            f"map SVG: marked {len(marked)} {what} for {len(partners)} partners; "
            f"missing: {', '.join(missing) or '-'}"
        )


def map_with_status(svg_text: str, partners: list[dict]) -> Markup:
    """The shared linked map with landing-only edits on a copy of its text.

    Each partner box gets data-status, and each partner label is (re)linked by
    partner_href(): the shared file links every enabled partner, the landing
    page only live and external ones. Text-level edits because the source SVG
    carries an invalid xmlns that lxml only reads in recover mode, and the
    original page inlines the file verbatim.
    """
    by_label = {p["label"]: p for p in partners}
    labels = [p["label"] for p in partners]

    svg = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", svg_text)
    svg = svg.replace("<svg", '<svg class="dp-map"', 1)

    marked_rects = []

    def mark(match: re.Match) -> str:
        label = match.group(1)
        if label not in by_label:
            return match.group(0)
        marked_rects.append(label)
        return f'{match.group(0)} data-status="{by_label[label]["status"]}"'

    svg = _RECT_LABEL.sub(mark, svg)
    _check_all_marked("partner boxes", marked_rects, labels)

    # Drop the links the generator put around partner labels ...
    svg = re.sub(
        r'<a\b[^>]*>(\s*<text\b[^>]*\binkscape:label="text_[a-z0-9-]+"[^>]*>.*?</text>\s*)</a>',
        r"\1",
        svg,
        flags=re.DOTALL,
    )

    # ... and link only where the landing rule says so.
    marked_texts = []

    def relink(match: re.Match) -> str:
        label = match.group(1)
        if label not in by_label:
            return match.group(0)
        marked_texts.append(label)
        partner = by_label[label]
        if not partner["href"]:
            return match.group(0)
        href = Markup.escape(partner["href"])
        title = Markup.escape(partner["name"])
        return f'<a xlink:href="{href}" xlink:title="{title}">{match.group(0)}</a>'

    svg = re.sub(
        r'<text\b[^>]*\binkscape:label="text_([a-z0-9-]+)"[^>]*>.*?</text>',
        relink,
        svg,
        flags=re.DOTALL,
    )
    _check_all_marked("partner labels", marked_texts, labels)

    return Markup(svg)


def render_landing(generator_root: Path, at_root: Path, linked_svg: Path, unis_csv: Path) -> Path:
    landing_dir = generator_root / "templates" / "landing"
    if not LANDING_BASE_PATH.startswith("/at/") or not LANDING_BASE_PATH.endswith("/"):
        raise LandingDataError(f"LANDING_BASE_PATH must start with /at/ and end with /: {LANDING_BASE_PATH!r}")
    out_dir = at_root / LANDING_BASE_PATH.removeprefix("/at/")

    svg_text = linked_svg.read_text(encoding="utf-8")
    partners = partner_labels(svg_text)

    with unis_csv.open(encoding="utf-8-sig", newline="") as fh:
        registry = {row["label"].strip(): row for row in csv.DictReader(fh)}
    names = {label: (row.get("Name") or "").strip() for label, row in registry.items()}
    repourls = {label: (row.get("repourl") or "").strip() for label, row in registry.items()}
    external = {label for label in partners if repourls.get(label)}

    rows = read_status_log(landing_dir / "status.csv", partners, external)
    news = read_news(landing_dir / "news.toml")
    strings = read_strings(landing_dir)

    current: dict[str, str] = {}
    for row in rows:
        current[row["label"]] = row["status"]

    dates = [row["datum"] for row in rows] + [item["datum"] for item in news]
    stand = max(dates) if dates else None
    steps = progress_steps(rows)
    # Partners with their own repository are shown but not counted.
    total = len(partners) - len(external)

    partner_list = []
    for label in partners:
        status = EXTERNAL if label in external else current.get(label, NO_STATUS)
        partner_list.append({
            "label": label,
            "name": names.get(label) or label,
            "status": status,
            "href": partner_href(label, status, repourls.get(label, "")),
        })

    env = Environment(
        loader=FileSystemLoader(str(landing_dir)),
        autoescape=select_autoescape(default=True, default_for_string=True),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    template = env.get_template("landing-jinja.html")

    urls = {lang: LANDING_BASE_PATH if lang == DEFAULT_LANGUAGE else f"{LANDING_BASE_PATH}{lang}/" for lang in LANGUAGES}
    map_markup = map_with_status(svg_text, partner_list)

    pages = {}
    for lang in LANGUAGES:
        s = strings[lang]
        fmt = s["date_format"]
        pages[lang] = template.render(
            lang=lang,
            s=s,
            urls=urls,
            default_lang=DEFAULT_LANGUAGE,
            css_href=f"{LANDING_BASE_PATH}landing.css",
            n=len(current),
            total=total,
            stand=stand.strftime(fmt) if stand else s["progress"]["no_date"],
            steps=[{"datum": st["datum"].strftime(fmt), "n": st["n"]} for st in steps],
            step_chart=step_chart_svg(steps, total, stand or date.today(), fmt, s["progress"]["chart_title"]),
            news=[{**item, "datum": item["datum"].strftime(fmt)} for item in news[:3]],
            partners=partner_list,
            map_svg=map_markup,
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(landing_dir / "landing.css", out_dir / "landing.css")
    if (landing_dir / "assets").is_dir():
        shutil.copytree(landing_dir / "assets", out_dir / "assets", dirs_exist_ok=True)
    for lang, html in pages.items():
        target = out_dir if lang == DEFAULT_LANGUAGE else out_dir / lang
        target.mkdir(parents=True, exist_ok=True)
        (target / "index.html").write_text(html, encoding="utf-8")

    print(f"[LANDING] Preview written to {out_dir} ({len(current)}/{total} partners with status, Stand {stand})")
    return out_dir
