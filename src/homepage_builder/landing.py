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
import struct
import sys
import tomllib
import unicodedata
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
# Shown on map and list instead of the progress status: per-university progress
# stays internal (links, counter, chart) so the page never singles out who is
# still waiting. Only "own repository" is a property worth showing.
PARTNER = "partner"
STATUS_HEADER = ["label", "status", "datum"]
NEWS_KEYS_REQUIRED = {"datum", "titel_de", "titel_en"}
NEWS_KEYS_OPTIONAL = {"text_de", "text_en", "link"}
LOGO_SUFFIXES = (".svg", ".png")
# Logos are scaled to the same visible area (px^2) so that wide and compact
# marks carry similar weight, then capped to the cell (max width, max height).
LOGO_AREA = {"partner": 4400, "org": 4200}
LOGO_MAX = {"partner": (150, 58), "org": (166, 48)}

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
    """Minimal step chart; the template shows the same data as a table.

    The margins leave room for labels up to 22 user units (landing.css
    enlarges them on narrow screens): the "0" label ends left of the axis,
    the date labels sit fully below the "0" label, the end date is
    right-aligned so the two dates never meet.
    """
    if not steps:
        return Markup("")

    width, height = 400, 200
    left, right, top, bottom = 46, 8, 14, 42
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
        f'<text class="axis-y" x="{left - 8}" y="{y(0):.1f}" text-anchor="end" dominant-baseline="middle" font-size="14">0</text>',
        f'<text class="axis-y" x="{left - 8}" y="{y(total):.1f}" text-anchor="end" dominant-baseline="middle" font-size="14">{total}</text>',
        f'<text class="axis-x" x="{left}" y="{height - 4}" font-size="14">{start.strftime(fmt)}</text>',
        f'<text class="axis-x" x="{width - right}" y="{height - 4}" text-anchor="end" font-size="14">{until.strftime(fmt)}</text>',
        f'<path d="{"".join(path)}" fill="none" stroke="currentColor" stroke-width="3"/>',
        "</svg>",
    ]
    return Markup("".join(parts))


def _sort_key(name: str) -> str:
    """Alphabetical order that files Ü under U and ignores case."""
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def localized_partners(partners: list[dict], display_names: dict) -> list[dict]:
    """Partners with the display name of one language, sorted by it.

    Display name = strings [names] entry, falling back to the registry name.
    """
    named = [{**p, "name": display_names.get(p["label"]) or p["name"]} for p in partners]
    return sorted(named, key=lambda p: _sort_key(p["name"]))


def own_space_shots(labels: list[str], partners: list[dict], shots_dir: Path) -> list[dict]:
    """Screenshot slots; src is None when the image is missing (neutral box)."""
    by_label = {p["label"]: p for p in partners}
    return [
        {
            "label": label,
            "name": by_label[label]["name"] if label in by_label else label,
            "src": f"{LANDING_BASE_PATH}assets/shots/{label}.webp" if (shots_dir / f"{label}.webp").is_file() else None,
        }
        for label in labels
    ]


_SVG_ROOT = re.compile(r"<svg\b[^>]*>", re.S)
_SVG_VIEWBOX = re.compile(r'viewBox\s*=\s*"([^"]+)"')
_SVG_LENGTH = {name: re.compile(rf'\s{name}\s*=\s*"([\d.]+)(?:px)?"') for name in ("width", "height")}


def _intrinsic_size(path: Path) -> tuple[float, float] | None:
    """Width and height from the PNG header or the SVG root viewBox."""
    if path.suffix.lower() == ".png":
        head = path.read_bytes()[:24]
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            width, height = struct.unpack(">II", head[16:24])
            return float(width), float(height)
        return None
    root = _SVG_ROOT.search(path.read_text(encoding="utf-8", errors="replace"))
    if not root:
        return None
    viewbox = _SVG_VIEWBOX.search(root.group(0))
    if viewbox:
        parts = [float(v) for v in re.split(r"[\s,]+", viewbox.group(1).strip())]
        if len(parts) == 4 and parts[2] > 0 and parts[3] > 0:
            return parts[2], parts[3]
    # No viewBox: fall back to absolute width/height (px or unitless).
    dims = [_SVG_LENGTH[name].search(root.group(0)) for name in ("width", "height")]
    if all(dims):
        width, height = (float(m.group(1)) for m in dims)
        if width > 0 and height > 0:
            return width, height
    return None


def _logo_size(size: tuple[float, float] | None, kind: str) -> tuple[int, int] | None:
    if not size:
        return None
    ratio = size[0] / size[1]
    width = (LOGO_AREA[kind] * ratio) ** 0.5
    height = width / ratio
    max_w, max_h = LOGO_MAX[kind]
    scale = min(1.0, max_w / width, max_h / height)
    return round(width * scale), round(height * scale)


def logo_files(logo_dir: Path) -> dict[str, dict]:
    """Logo per key (file stem, e.g. a partner label) with its display size.

    Missing keys render as text placeholders. Empty margins inside the files
    distort the balance; crop them before adding a logo.
    """
    if not logo_dir.is_dir():
        return {}
    logos = {}
    for path in sorted(logo_dir.iterdir()):
        if path.suffix.lower() not in LOGO_SUFFIXES:
            continue
        size = _intrinsic_size(path)
        logos[path.stem] = {
            "src": f"{LANDING_BASE_PATH}assets/logos/{path.name}",
            "partner": _logo_size(size, "partner"),
            "org": _logo_size(size, "org"),
        }
    return logos


def partner_href(label: str, status: str, repourl: str, has_space: bool) -> str | None:
    """One link rule for map, logo strip and list.

    External partners link to their own repository. Everyone else links to
    /at/<label>/ once the space is set up (any status) and its page exists in
    this build, so a status ahead of the server never produces a dead link.
    """
    if status == EXTERNAL:
        return repourl
    if status in STATUSES and has_space:
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

    Each partner box gets data-status (partner or external, not the progress
    status), and each partner label is (re)linked by
    partner_href(): the shared file links every enabled partner, the landing
    page only set-up spaces that exist in this build and external repositories. Text-level edits because the source SVG
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
        return f'{match.group(0)} data-status="{by_label[label]["shown"]}"'

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

    # "Stand" never runs ahead of the build: future-dated news stay listed but
    # do not count. The chart's x-axis likewise ends at the build date.
    build_date = date.today()
    dates = [row["datum"] for row in rows] + [item["datum"] for item in news]
    past = [d for d in dates if d <= build_date]
    stand = max(past) if past else None
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
            "shown": EXTERNAL if status == EXTERNAL else PARTNER,
            "href": partner_href(label, status, repourls.get(label, ""), (at_root / label / "index.html").is_file()),
        })

    env = Environment(
        loader=FileSystemLoader(str(landing_dir)),
        autoescape=select_autoescape(default=True, default_for_string=True),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    template = env.get_template("landing-jinja.html")
    css_href = f"{LANDING_BASE_PATH}landing.css"

    urls = {lang: LANDING_BASE_PATH if lang == DEFAULT_LANGUAGE else f"{LANDING_BASE_PATH}{lang}/" for lang in LANGUAGES}
    map_markup = map_with_status(svg_text, partner_list)
    logos = logo_files(landing_dir / "assets" / "logos")

    # Plain pages (legal notice, privacy, accessibility; German) and the user
    # guide (English). Rendered before the landing so that links only point to
    # pages that rendered; a problem here skips those pages, never the landing.
    try:
        from . import landing_guide
    except ImportError:
        try:
            import landing_guide
        except Exception as exc:  # e.g. Markdown not installed
            landing_guide = None
            print(f"[LANDING] Guide and pages skipped: {exc}", file=sys.stderr)
    except Exception as exc:
        landing_guide = None
        print(f"[LANDING] Guide and pages skipped: {exc}", file=sys.stderr)

    shared = {"urls": urls, "default_lang": DEFAULT_LANGUAGE, "css_href": css_href}
    plain = None
    legal_urls: dict[str, str] = {}
    guide = None
    guide_url = None
    if landing_guide:
        try:
            plain = landing_guide.render_pages(
                env, landing_dir / "pages", strings["de"], {**shared, "guide_url": f"{LANDING_BASE_PATH}guide/"}, LANDING_BASE_PATH
            )
            legal_urls = plain["urls"]
        except Exception as exc:
            plain = None
            print(f"[LANDING] Pages skipped: {exc}", file=sys.stderr)
        try:
            guide_url = f"{LANDING_BASE_PATH}guide/"
            guide = landing_guide.render_guide(
                env,
                landing_dir / "guide",
                strings["en"],
                {**shared, "guide_url": guide_url, "legal_urls": legal_urls},
                LANDING_BASE_PATH,
            )
        except Exception as exc:
            guide, guide_url = None, None
            print(f"[LANDING] Guide skipped: {exc}", file=sys.stderr)
        if plain and not guide:
            # Pages were rendered with a guide link; re-render without it.
            plain = landing_guide.render_pages(env, landing_dir / "pages", strings["de"], {**shared, "guide_url": None}, LANDING_BASE_PATH)

    pages = {}
    for lang in LANGUAGES:
        s = strings[lang]
        fmt = s["date_format"]
        lang_partners = localized_partners(partner_list, s.get("names", {}))
        pages[lang] = template.render(
            lang=lang,
            s=s,
            urls=urls,
            default_lang=DEFAULT_LANGUAGE,
            css_href=css_href,
            guide_url=guide_url,
            alt_url=urls[s["lang_switch_lang"]],
            current="landing",
            legal_urls=legal_urls,
            n=len(current),
            total=total,
            stand=stand.strftime(fmt) if stand else s["progress"]["no_date"],
            steps=[{"datum": st["datum"].strftime(fmt), "n": st["n"]} for st in steps],
            step_chart=step_chart_svg(steps, total, build_date, fmt, s["progress"]["chart_title"]),
            news=[{**item, "datum": item["datum"].strftime(fmt)} for item in news[:3]],
            partners=lang_partners,
            shots=own_space_shots(s["own_space"]["shots"], lang_partners, landing_dir / "assets" / "shots"),
            map_svg=map_markup,
            logos=logos,
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(landing_dir / "landing.css", out_dir / "landing.css")
    if (landing_dir / "assets").is_dir():
        shutil.copytree(landing_dir / "assets", out_dir / "assets", dirs_exist_ok=True)
    for lang, html in pages.items():
        target = out_dir if lang == DEFAULT_LANGUAGE else out_dir / lang
        target.mkdir(parents=True, exist_ok=True)
        (target / "index.html").write_text(html, encoding="utf-8")

    if plain:
        for rel, html in plain["pages"].items():
            target = out_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(html, encoding="utf-8")
        print(f"[LANDING] Pages written: {', '.join(sorted(plain['urls']))}")
    if guide:
        for rel, html in guide["pages"].items():
            target = out_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(html, encoding="utf-8")
        if guide["uploads"].is_dir():
            shutil.copytree(guide["uploads"], out_dir / "guide" / "uploads", dirs_exist_ok=True)
        print(f"[LANDING] Guide written: {len(guide['pages'])} pages, {len(guide['warnings'])} warnings")
        for warning in guide["warnings"]:
            print(f"[LANDING] Guide warning: {warning}")

    print(f"[LANDING] Preview written to {out_dir} ({len(current)}/{total} partners with status, Stand {stand})")
    return out_dir
