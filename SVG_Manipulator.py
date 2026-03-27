from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple, Optional

import pandas as pd
from lxml import etree


@dataclass
class SVGLinkConfig:
    # Paths are relative to template_dir
    source_svg_rel: str = "pagedata/DP.svg"
    csv_rel_path: str = "conf/unis.csv"
    cache_rel_dir: str = "cache/img"
    out_name: str = "DP.linked.svg"
    Arecord: bool = True
    local_test: bool = False
    # Runtime / behavior
    server_name: str = ""              # e.g. "bonndata.uni-bonn.de" (NO scheme needed)
    target_attr: str = "blank"         # your example uses target="blank"
    require_enabled_column: bool = False  # if True and enabled missing -> treat as disabled



class SVGManipulator:
    """
    Creates a cached 'linked' version of an SVG by wrapping
    <text inkscape:label="text_{label}"> nodes in <a xlink:href="...">,
    using link info from a CSV (label, Name, repourl, enabled).
    """

    INKSCAPE_NS = "http://www.inkscape.org/namespaces/inkscape"
    XLINK_NS = "http://www.w3.org/1999/xlink"
    SVG_NS = "http://www.w3.org/2000/svg"

    NS = {
        "svg": SVG_NS,
        "inkscape": INKSCAPE_NS,
        "xlink": XLINK_NS,
    }

    def __init__(self, template_dir: str | Path, config: Optional[SVGLinkConfig] = None):
        self.template_dir = Path(template_dir).resolve()
        self.config = config or SVGLinkConfig()

    # ---------- path helpers ----------

    def source_svg_path(self) -> Path:
        return (self.template_dir / self.config.source_svg_rel).resolve()

    def csv_path(self) -> Path:
        return (self.template_dir / self.config.csv_rel_path).resolve()

    def cache_dir(self) -> Path:
        return (self.template_dir / self.config.cache_rel_dir).resolve()

    def cached_svg_path(self) -> Path:
        return self.cache_dir() / self.config.out_name

    def ensure_cache_dir(self) -> Path:
        d = self.cache_dir()
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ---------- core logic ----------

    @staticmethod
    def _normalize_server_name(server_name: str) -> str:
        s = (server_name or "").strip()
        s = s.removeprefix("https://").removeprefix("http://")
        return s.strip("/")

    def _fallback_url(self, label: str) -> str:
        server = self._normalize_server_name(self.config.server_name)
        if not server:
            raise ValueError(
                "server_name is required for fallback URL (repourl empty). "
                "Set SVGLinkConfig(server_name='bonndata.uni-bonn.de')."
            )
        if self.config.Arecord:
            return f"https://{label}.{server}"
        else:
            if self.config.local_test:
                return f"{label}"
            else:
                return f"https://{server}/{label}"

    def _read_csv_rows(self) -> Dict[str, Tuple[int, str, str]]:
        """
        Returns mapping: label -> (enabled_int, url, title)

        Rules:
        - enabled must be 1 to create/update a link (if enabled column exists).
        - link comes from repourl, but if empty -> https://{label}.{server_name}
        - title from Name (optional)
        """
        csv_path = self.csv_path()
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV not found: {csv_path}")

        df = pd.read_csv(str(csv_path), delimiter=",", quotechar='"')

        has_enabled = "enabled" in df.columns

        mapping: Dict[str, Tuple[int, str, str]] = {}
        for _, row in df.iterrows():
            label = str(row.get("label", "")).strip()
            if not label:
                continue

            # enabled logic
            if has_enabled:
                try:
                    enabled = int(row.get("enabled", 0))
                except Exception:
                    enabled = 0
            else:
                enabled = 0 if self.config.require_enabled_column else 1

            name = str(row.get("Name", "")).strip()

            repourl = row.get("repourl")
            repourl = repourl.strip() if isinstance(repourl, str) else ""

            # URL rule (always compute url; apply enabled check later)
            url = repourl if repourl else self._fallback_url(label)

            mapping[label] = (enabled, url, name)

        return mapping

    def _wrap_or_update_text_node(self, text_el: etree._Element, url: str, title: str) -> bool:
        """
        Ensures text_el is wrapped in <a>. If already wrapped, updates it.
        Returns True if it was already wrapped, False if newly wrapped.
        """
        parent = text_el.getparent()
        if parent is None:
            return False

        if etree.QName(parent).localname == "a":
            parent.set(f"{{{self.XLINK_NS}}}href", url)
            parent.set("target", self.config.target_attr)
            if title:
                parent.set(f"{{{self.XLINK_NS}}}title", title)
            return True

        a = etree.Element(f"{{{self.SVG_NS}}}a")
        a.set(f"{{{self.XLINK_NS}}}href", url)
        a.set("target", self.config.target_attr)
        if title:
            a.set(f"{{{self.XLINK_NS}}}title", title)

        idx = parent.index(text_el)
        parent.remove(text_el)
        parent.insert(idx, a)
        a.append(text_el)
        return False

    def generate_linked_svg(self, out_path: str | Path) -> dict:
        """
        Always generate out_path (overwrite). Returns stats.
        """
        source_svg = self.source_svg_path()
        if not source_svg.exists():
            raise FileNotFoundError(f"SVG not found: {source_svg}")

        out_path = Path(out_path)
        rows = self._read_csv_rows()

        parser = etree.XMLParser(remove_blank_text=False, recover=True)
        tree = etree.parse(str(source_svg), parser)
        root = tree.getroot()

        stats = {
            "wrapped": 0,
            "updated": 0,
            "missing_text": 0,
            "skipped_disabled": 0,
        }

        for label, (enabled, url, title) in rows.items():
            target_label = f"text_{label}"

            text_nodes = root.xpath(
                f'//svg:text[@inkscape:label="{target_label}"]',
                namespaces=self.NS,
            )

            if not text_nodes:
                stats["missing_text"] += 1
                continue

            # NEW RULE: only link when enabled == 1
            if enabled != 1:
                stats["skipped_disabled"] += len(text_nodes)
                continue

            for text_el in text_nodes:
                already_wrapped = self._wrap_or_update_text_node(text_el, url, title)
                if already_wrapped:
                    stats["updated"] += 1
                else:
                    stats["wrapped"] += 1

        out_path.parent.mkdir(parents=True, exist_ok=True)
        tree.write(str(out_path), encoding="utf-8", xml_declaration=True)
        return stats

    def ensure_linked_svg(self, use_cache=False) -> Path:
        """
        Generate the cached linked SVG only if it doesn't exist yet.
        Returns the path to the cached SVG.
        """
        self.ensure_cache_dir()
        out_svg = self.cached_svg_path()
        if use_cache and out_svg.exists():
            return out_svg

        self.generate_linked_svg(out_path=out_svg)
        return out_svg
