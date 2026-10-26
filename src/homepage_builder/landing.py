"""Render the new consortium landing page (hidden preview, one page per language).

Inputs live in templates/landing/:
  landing-jinja.html   the page template, rendered once per language
  landing.css          copied next to the rendered pages
  strings.<lang>.toml  all visible text
  news.toml            [[news]] entries
  status.csv           append-only log: label,status,datum
  map/DP.landing.svg   SVGO derivative of the shared map DP.svg (map/svgo.config.mjs)

The caller wraps render_landing() so that bad landing data only skips the
preview; nothing is written unless both languages render.
"""
from __future__ import annotations

import csv
import hashlib
import re
import shutil
import struct
import subprocess
import sys
import tomllib
import unicodedata
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit
from zoneinfo import ZoneInfo

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
LOGO_MAX = {"partner": (158, 58), "org": (166, 48)}
# Equal area still left a 3.4x spread in visual weight, so the area-based size
# is multiplied by an optical factor per key before the caps. Measured
# 2026-10-26 on a6832df: ink = sum of (1 - luma) over pixels with luma < 0.92,
# each logo rendered at 2x at its displayed partner size; factor =
# clamp((median / ink) ** (1/3), 0.85, 1.15), median over the partner strip;
# kept only where |factor - 1| >= 0.05. Table: DESIGN-NOTES.md (landing-preview).
LOGO_OPTICAL: dict[str, float] = {
    "h-brs": 1.13,
    "hs-bochum": 1.07,
    "uni-koeln": 1.06,
    "th-koeln": 0.95,
    "uni-wuppertal": 0.87,
    "uni-siegen": 0.87,
    "hsbi": 0.85,
    "uni-bielefeld": 0.85,
    "rwth-aachen": 0.88,
}
# Fixed display width per (kind, key), instead of area, factor and caps:
# the ministry name inside the MKW mark is unreadable at the area size.
LOGO_WIDTH = {("org", "mkw"): 220}

# The map is a size-optimized derivative of the shared DP.svg, made with SVGO
# (a local dev tool) and checked in. The .sha256 file records which DP.svg it
# was made from; the regeneration command is the "// $ " line of the config.
MAP_SOURCE = Path("templates/assets/pagedata/DP.svg")
MAP_DERIVATIVE = Path("templates/landing/map/DP.landing.svg")
MAP_SOURCE_HASH = Path("templates/landing/map/DP.landing.svg.sha256")
MAP_SVGO_CONFIG = Path("templates/landing/map/svgo.config.mjs")

# Build line in the footer: render date in this zone.
BUILD_TIMEZONE = ZoneInfo("Europe/Berlin")
BUILD_INFO_SEPARATOR = " · "
# The page weight in the build line is part of the page it measures: render
# until the shown value is the value of the page that shows it.
WEIGHT_PASSES = 3

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


def _logo_size(size: tuple[float, float] | None, kind: str, key: str) -> tuple[int, int] | None:
    if not size:
        return None
    ratio = size[0] / size[1]
    if (kind, key) in LOGO_WIDTH:
        width = LOGO_WIDTH[kind, key]
        return width, round(width / ratio)
    width = (LOGO_AREA[kind] * ratio) ** 0.5 * LOGO_OPTICAL.get(key, 1.0)
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
            "partner": _logo_size(size, "partner", path.stem),
            "org": _logo_size(size, "org", path.stem),
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


def landing_map_svg(generator_root: Path) -> str:
    """Text of the landing map derivative, refused when DP.svg has changed since it was made."""
    source = generator_root / MAP_SOURCE
    recorded = (generator_root / MAP_SOURCE_HASH).read_text(encoding="utf-8").strip()
    actual = hashlib.sha256(source.read_bytes()).hexdigest()
    if recorded != actual:
        config = (generator_root / MAP_SVGO_CONFIG).read_text(encoding="utf-8")
        command = next((line[len("// $ "):] for line in config.splitlines() if line.startswith("// $ ")), None)
        raise LandingDataError(
            f"{MAP_DERIVATIVE} is stale: made from DP.svg {recorded[:12]}, current DP.svg is {actual[:12]}. "
            f"Regenerate from the subdataversehp root: {command or f'see {MAP_SVGO_CONFIG}'}"
        )
    return (generator_root / MAP_DERIVATIVE).read_text(encoding="utf-8")


def map_with_status(svg_text: str, partners: list[dict]) -> Markup:
    """The landing map derivative with landing-only edits on a copy of its text.

    Each partner box gets data-status (partner or external, not the progress
    status), and each partner label is (re)linked by partner_href(): DP.svg
    links some partners, the landing page only set-up spaces that exist in
    this build and external repositories. Text-level edits because DP.svg
    carries an invalid xmlns that lxml only reads in recover mode, and the
    original page inlines that file verbatim.
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

    # Drop the links DP.svg has around partner labels ...
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


def generator_revision(generator_root: Path) -> str | None:
    """`git rev-parse --short HEAD` of the generator checkout, "-dirty" if tracked files differ.

    None (with a warning) without git. The server and build.sh build in a copy
    without .git; that copy may sit inside another checkout, whose HEAD must
    not be shown, hence the toplevel check.
    """
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(generator_root), *args], capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip()

    try:
        toplevel = Path(git("rev-parse", "--show-toplevel")).resolve()
        if toplevel != generator_root.resolve():
            raise subprocess.SubprocessError(f"{generator_root} is not a checkout (enclosing repository {toplevel})")
        revision = git("rev-parse", "--short", "HEAD")
        if git("status", "--porcelain", "--untracked-files=no"):
            revision += "-dirty"
    except subprocess.CalledProcessError as exc:
        reason = exc.stderr.strip().splitlines()[0] if exc.stderr.strip() else exc
        print(f"[LANDING] Warning: build line without hash: {reason}", file=sys.stderr)
        return None
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"[LANDING] Warning: build line without hash: {exc}", file=sys.stderr)
        return None
    return revision


def kilobytes(size: int, thousands_separator: str) -> str:
    """Bytes as whole kB (1000 bytes, rounded up): 1028989 -> "1.029 kB" with "."."""
    return f"{-(-size // 1000):,} kB".replace(",", thousands_separator)


def build_info_segments(template: str, day: date, date_format: str, revision: str | None, size: str) -> list[Markup]:
    """Footer build line from strings: {size}, {date} as <time>, the {hash} segment dropped without a revision."""
    when = Markup('<time datetime="{}">{}</time>').format(day.isoformat(), day.strftime(date_format))
    segments = []
    for segment in template.split(BUILD_INFO_SEPARATOR):
        if "{hash}" in segment and revision is None:
            continue
        segments.append(
            Markup.escape(segment).replace("{size}", size).replace("{date}", when).replace("{hash}", revision or "")
        )
    return segments


# Attributes, <link rel> values and SVG elements whose URLs the browser fetches while loading the page.
_LOADING_ATTRS = {"src", "srcset", "poster", "data", "imagesrcset"}
_LOADING_RELS = {"stylesheet", "preload", "modulepreload", "prefetch", "icon", "apple-touch-icon", "mask-icon", "manifest"}
_SVG_HREF_ELEMENTS = {"image", "feimage", "use"}
_CSS_URL = re.compile(r"""url\(\s*(?:"([^"]*)"|'([^']*)'|([^)\s]*))\s*\)|@import\s+(?:"([^"]*)"|'([^']*)')""")


def _css_urls(css: str) -> list[str]:
    return [next(group for group in match.groups() if group is not None) for match in _CSS_URL.finditer(css)]


class _PageScan(HTMLParser):
    """Claim violations and loaded resources (url, base) of one rendered page."""

    def __init__(self, page_url: str):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.violations: list[str] = []
        self.resources: list[tuple[str, str]] = []
        self._in_style = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "script" and (values.get("type") or "").strip().lower() != "application/ld+json":
            self.violations.append(f"<script type={values.get('type')!r}>")
        for name, value in attrs:
            if name.startswith("on"):
                self.violations.append(f"<{tag} {name}=...> event attribute")
            if value and re.sub(r"[\x00-\x20]", "", value).lower().startswith("javascript:"):
                self.violations.append(f"<{tag} {name}={value[:40]!r}> javascript: URL")
        urls = []
        for name, value in attrs:
            if not value:
                continue
            if name in ("srcset", "imagesrcset"):
                urls += [candidate.split()[0] for candidate in value.split(",") if candidate.strip()]
            elif name in _LOADING_ATTRS:
                urls.append(value)
            elif name == "style":
                urls += _css_urls(value)
        if tag == "link" and set((values.get("rel") or "").lower().split()) & _LOADING_RELS and values.get("href"):
            urls.append(values["href"])
        if tag in _SVG_HREF_ELEMENTS:
            urls += [value for name, value in attrs if name in ("href", "xlink:href") and value]
        self.resources += [(url.strip(), self.page_url) for url in urls]
        self._in_style = tag == "style"

    def handle_endtag(self, tag):
        self._in_style = False

    def handle_data(self, data):
        if self._in_style:
            self.resources += [(url.strip(), self.page_url) for url in _css_urls(data)]


def _is_local(url: str) -> bool:
    """Relative or root-relative: no scheme, no host (browsers read a backslash as a slash)."""
    parts = urlsplit(url.replace("\\", "/"))
    return not parts.scheme and not parts.netloc


def check_page(html: str, page_url: str, css_files: dict[str, str]) -> tuple[list[str], list[str]]:
    """Enforce the footer claims on one rendered page; returns (violations, loaded paths).

    "No JavaScript": no <script> other than JSON-LD, no on* attributes, no
    javascript: URLs. "No third-party requests": every loaded resource (src,
    srcset, <link> stylesheet/preload/icon, CSS url() in landing.css and inline
    styles) is relative or root-relative. "No cookies" cannot be checked at
    build time: the page cannot set one without JavaScript, and the server sent
    no Set-Cookie for the preview when checked by hand on 2026-10-21
    (curl -sI <url> | grep -i set-cookie -> empty).
    """
    scan = _PageScan(page_url)
    scan.feed(html)
    scan.close()
    pending = list(scan.resources)
    violations = list(scan.violations)
    loaded: list[str] = []
    while pending:
        url, base = pending.pop(0)
        if url.startswith("#"):  # same-document reference (<use href="#…">, url(#…)), nothing loaded
            continue
        if not _is_local(url):
            violations.append(f"external resource {url!r}")
            continue
        absolute = urlsplit(urljoin(base, url)).path
        if absolute in loaded:
            continue
        loaded.append(absolute)
        if absolute in css_files:
            pending += [(nested, absolute) for nested in _css_urls(css_files[absolute])]
    return violations, loaded


def page_weight(html: str, loaded: list[str], landing_dir: Path) -> tuple[int, int, int]:
    """(total, html, files) in bytes: the page plus every file it loads, each once.

    The files are counted at their source in templates/landing/, of which
    landing.css and assets/ are copied unchanged next to the pages.
    """
    files = 0
    for path in loaded:
        relative = unquote(path).removeprefix(LANDING_BASE_PATH) if path.startswith(LANDING_BASE_PATH) else None
        source = landing_dir / relative if relative and (relative == "landing.css" or relative.startswith("assets/")) else None
        if source is None or not source.is_file():
            raise LandingDataError(f"page loads {path}, which the build does not publish")
        files += source.stat().st_size
    html_bytes = len(html.encode("utf-8"))
    return html_bytes + files, html_bytes, files


def render_landing(generator_root: Path, at_root: Path, unis_csv: Path) -> Path:
    landing_dir = generator_root / "templates" / "landing"
    if not LANDING_BASE_PATH.startswith("/at/") or not LANDING_BASE_PATH.endswith("/"):
        raise LandingDataError(f"LANDING_BASE_PATH must start with /at/ and end with /: {LANDING_BASE_PATH!r}")
    out_dir = at_root / LANDING_BASE_PATH.removeprefix("/at/")

    svg_text = landing_map_svg(generator_root)
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
    build_date = datetime.now(BUILD_TIMEZONE).date()
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

    revision = generator_revision(generator_root)

    def render_page(lang: str, size: str) -> str:
        s = strings[lang]
        fmt = s["date_format"]
        lang_partners = localized_partners(partner_list, s.get("names", {}))
        return template.render(
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
            build_info=build_info_segments(
                s["footer"]["build_info"], build_date, s["footer"]["build_date_format"], revision, size
            ),
        )

    # Render, weigh, substitute the weight, and repeat until the shown kB are
    # those of the page that shows them. The first pass shows "0 kB".
    css_files = {css_href: (landing_dir / "landing.css").read_text(encoding="utf-8")}
    pages = {}
    weights = {}
    for lang in LANGUAGES:
        separator = strings[lang]["footer"]["build_thousands_separator"]
        size = kilobytes(0, separator)
        shown = []
        for _ in range(WEIGHT_PASSES):
            shown.append(size)
            html = render_page(lang, size)
            violations, loaded = check_page(html, urls[lang], css_files)
            if violations:
                raise LandingDataError(f"{lang} page breaks its footer claims: " + "; ".join(violations))
            weight = page_weight(html, loaded, landing_dir)
            measured = kilobytes(weight[0], separator)
            if measured == size:
                pages[lang], weights[lang] = html, weight
                break
            size = measured
        else:
            raise LandingDataError(
                f"{lang} page weight did not settle in {WEIGHT_PASSES} passes (shown {', '.join(shown)}, measured {size})"
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

    for lang, (weight, html_bytes, files) in weights.items():
        print(f"[LANDING] page weight {lang}: {weight} B (HTML {html_bytes} B + files {files} B)")
    print(f"[LANDING] Preview written to {out_dir} ({len(current)}/{total} partners with status, Stand {stand})")
    return out_dir
