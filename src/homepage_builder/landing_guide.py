"""User guide and plain pages (legal notice, privacy, accessibility) for the landing preview.

Both are Markdown rendered in the landing layout.

Guide
 source: templates/landing/guide/, a GitLab-wiki tree:
  - one .md per page with YAML front matter `title:`; children of Foo.md live in Foo/
  - images under uploads/<hash>/<file>
  - page links as root links (/Path/Page, braces may be URL-encoded)
  - order.txt (optional): page paths without .md, one per line, in navigation
    order; pages not listed follow, sorted by title

Rendering rules:
  - <DP-NAME> placeholders and [DP-TODO-nn] notes become highlighted marks, so
    open points stay visible in the preview (code spans and blocks are left as is)
  - external images are not loaded (no third-party requests); a marked note names
    the URL instead
  - broken internal links are reported, never fatal

Plain pages: templates/landing/pages/<slug>.md -> <base>/<slug>/ (German only).

render_guide() and render_pages() only return HTML; landing.render_landing()
writes it.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

import markdown  # requirements.txt: Markdown
from markupsafe import Markup

ROOT_PAGE = "DataPublication-User-Guide-v1.0.0"
REFERENCES = "references"

_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
_TITLE = re.compile(r"^title:\s*(.+?)\s*$", re.M)
_CODE = re.compile(r"(```.*?```|`[^`\n]*`)", re.S)
_PLACEHOLDER = re.compile(r"<{1,2}(DP-[A-Z][A-Z-]*)>{1,2}")
_TODO = re.compile(r"\[(DP-TODO-[A-Z]?\d+)\]")
_ROOT_LINK = re.compile(r"\]\((/[^)\s]+)\)")
_EXT_IMG_MD = re.compile(r"!\[([^\]]*)\]\((https?://[^)\s]+)\)")
_EXT_IMG_HTML = re.compile(r'<img\b[^>]*\bsrc="(https?://[^"]+)"[^>]*>')
_CALLOUT = re.compile(r"<p><strong>(Hint|Please note|Note|Warning)\b")
_CALLOUT_KIND = {"Hint": "hint", "Please note": "note", "Note": "note", "Warning": "warning"}
_TODO_QUOTE = re.compile(r'<blockquote>(\s*<p>(?:<strong>)?<mark class="todo">)')


def page_slug(rel: str) -> str:
    """URL slug: drop the root page folder, braces and the 'DataPublication-' prefix."""
    parts = rel.split("/")
    if parts[0] == ROOT_PAGE:
        parts = parts[1:]
    cleaned = []
    for part in parts:
        part = re.sub(r"^DataPublication-", "", part.replace("{", "").replace("}", ""))
        cleaned.append(re.sub(r"[^a-z0-9.]+", "-", part.lower()).strip("-"))
    return "/".join(cleaned)


def _title_and_body(text: str, fallback: str) -> tuple[str, str]:
    front = _FRONT.match(text)
    if not front:
        return fallback, text
    title = _TITLE.search(front.group(1))
    value = title.group(1).strip().strip("'\"").strip() if title else ""
    return value or fallback, text[front.end():]


def _outside_code(text: str, transform) -> str:
    parts = _CODE.split(text)
    return "".join(part if i % 2 else transform(part) for i, part in enumerate(parts))


def _load(guide_dir: Path) -> dict[str, dict]:
    pages = {}
    for path in sorted(guide_dir.rglob("*.md")):
        rel = path.relative_to(guide_dir).with_suffix("").as_posix()
        if rel.startswith("uploads/"):
            continue
        fallback = path.stem.replace("{", "").replace("}", "").replace("-", " ")
        title, body = _title_and_body(path.read_text(encoding="utf-8"), fallback)
        pages[rel] = {"rel": rel, "title": title, "body": body, "children": []}
    if ROOT_PAGE not in pages:
        raise FileNotFoundError(f"guide: {ROOT_PAGE}.md not found in {guide_dir}")
    return pages


def _order(guide_dir: Path) -> dict[str, int]:
    order_file = guide_dir / "order.txt"
    if not order_file.is_file():
        return {}
    lines = [line.strip() for line in order_file.read_text(encoding="utf-8").splitlines()]
    return {line: i for i, line in enumerate(line for line in lines if line and not line.startswith("#"))}


def render_guide(env, guide_dir: Path, s: dict, context: dict, base_path: str) -> dict:
    """Render all guide pages. Returns {"pages": {out_rel: html}, "uploads": Path, "warnings": [...]}.

    context: variables shared with the landing templates (urls, default_lang,
    css_href, guide_url); s: the strings of the guide's language.
    """
    pages = _load(guide_dir)
    order = _order(guide_dir)
    guide_base = f"{base_path}guide/"

    for page in pages.values():
        slug = page_slug(page["rel"])
        page["url"] = f"{guide_base}{slug}/" if slug else guide_base
        page["out"] = f"guide/{slug}/index.html" if slug else "guide/index.html"

    def sort_key(page):
        return (order.get(page["rel"], len(order)), page["title"].lower())

    root = pages[ROOT_PAGE]
    references = []
    for rel, page in pages.items():
        if rel == ROOT_PAGE:
            continue
        parent_rel = rel.rsplit("/", 1)[0] if "/" in rel else None
        if parent_rel in pages:
            pages[parent_rel]["children"].append(page)
        elif rel.startswith(f"{REFERENCES}/"):
            references.append(page)
        else:
            root["children"].append(page)
    for page in pages.values():
        page["children"].sort(key=sort_key)
    references.sort(key=sort_key)

    sequence = []

    def walk(page):
        sequence.append(page)
        for child in page["children"]:
            walk(child)

    walk(root)
    for page in references:
        walk(page)

    def node(page):
        return {"title": page["title"], "url": page["url"], "children": [node(c) for c in page["children"]]}

    nav = {"main": [node(root)], "references": [node(p) for p in references]}

    by_target = {rel: page["url"] for rel, page in pages.items()}
    warnings = []
    converter = markdown.Markdown(
        extensions=["extra", "toc", "sane_lists"],
        extension_configs={"toc": {"toc_depth": "2-4"}},
        output_format="html",
    )

    def prepare(page):
        def link(match):
            target, _, anchor = unquote(match.group(1)).lstrip("/").partition("#")
            url = by_target.get(target.rstrip("/"))
            if url is None:
                warnings.append(f"{page['rel']}: broken link /{target}")
                return match.group(0)
            return f"]({url}{'#' + anchor if anchor else ''})"

        def external_image(match):
            url = match.group(2) if match.lastindex and match.lastindex >= 2 else match.group(1)
            warnings.append(f"{page['rel']}: external image not loaded: {url}")
            return f'<mark class="todo">External image not loaded: {url}</mark>'

        def transform(text):
            text = _PLACEHOLDER.sub(r'<mark class="todo">\1</mark>', text)
            text = _TODO.sub(r'<mark class="todo">\1</mark>', text)
            text = _EXT_IMG_MD.sub(external_image, text)
            text = _EXT_IMG_HTML.sub(external_image, text)
            text = _ROOT_LINK.sub(link, text)
            text = text.replace("](uploads/", f"]({guide_base}uploads/")
            return text.replace('src="uploads/', f'src="{guide_base}uploads/')

        return _outside_code(page["body"], transform)

    out = {}
    template = env.get_template("guide-jinja.html")
    for i, page in enumerate(sequence):
        html = converter.reset().convert(prepare(page))
        html = _CALLOUT.sub(lambda m: f'<p class="callout callout-{_CALLOUT_KIND[m.group(1)]}"><strong>{m.group(1)}', html)
        html = _TODO_QUOTE.sub(r'<blockquote class="todo-note">\1', html)
        html = html.replace("<img ", '<img loading="lazy" ')
        out[page["out"]] = template.render(
            **{k: v for k, v in context.items() if k != "legal_urls"},
            s=s,
            lang="en",
            current="guide",
            legal_urls=context.get("legal_urls", {}),
            alt_url=None,
            nav=nav,
            page={
                "title": page["title"],
                "url": page["url"],
                "html": Markup(html),
                "children": [{"title": c["title"], "url": c["url"]} for c in page["children"]],
            },
            prev=({"title": sequence[i - 1]["title"], "url": sequence[i - 1]["url"]} if i > 0 else None),
            next=({"title": sequence[i + 1]["title"], "url": sequence[i + 1]["url"]} if i + 1 < len(sequence) else None),
            todo_count=html.count('<mark class="todo">'),
        )
    return {"pages": out, "uploads": guide_dir / "uploads", "warnings": warnings}


def _markers(text: str) -> str:
    text = _PLACEHOLDER.sub(r'<mark class="todo">\1</mark>', text)
    return _TODO.sub(r'<mark class="todo">\1</mark>', text)


def render_pages(env, pages_dir: Path, s: dict, context: dict, base_path: str) -> dict:
    """Render templates/landing/pages/*.md. Returns {"pages": {out_rel: html}, "urls": {slug: url}}."""
    if not pages_dir.is_dir():
        return {"pages": {}, "urls": {}}
    converter = markdown.Markdown(extensions=["extra", "toc", "sane_lists"], output_format="html")
    sources = sorted(path for path in pages_dir.glob("*.md"))
    urls = {path.stem: f"{base_path}{path.stem}/" for path in sources}
    template = env.get_template("page-jinja.html")
    out = {}
    for path in sources:
        title, body = _title_and_body(path.read_text(encoding="utf-8"), path.stem)
        html = converter.reset().convert(_outside_code(body, _markers))
        html = _TODO_QUOTE.sub(r'<blockquote class="todo-note">\1', html)
        out[f"{path.stem}/index.html"] = template.render(
            **context,
            s=s,
            lang="de",
            current="page",
            alt_url=None,
            legal_urls=urls,
            page={"title": title, "url": urls[path.stem], "html": Markup(html)},
            todo_count=html.count('<mark class="todo">'),
        )
    return {"pages": out, "urls": urls}
