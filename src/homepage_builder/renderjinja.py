from __future__ import annotations
from urllib.parse import quote
import argparse
import json
import random
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from jinja2 import ChoiceLoader, Environment, FileSystemLoader
from markupsafe import Markup

try:
    from .dataverse_api import DataverseAPI
    from .dataverse_template import FALLBACK_IMAGE_SRC, DataverseTemplate
    from .svg_manipulator import SVGLinkConfig, SVGManipulator
except ImportError:
    from dataverse_api import DataverseAPI
    from dataverse_template import FALLBACK_IMAGE_SRC, DataverseTemplate
    from svg_manipulator import SVGLinkConfig, SVGManipulator


# ---------------------------------------------------------------------------
# Sidebar box on every /at/<label>/ page ("Before your first dataset").
# Audience: researchers of the university who are about to publish for the
# first time. The box links into the user guide instead of repeating it.
#
# GUIDE_BASE must follow landing.LANDING_BASE_PATH + "guide/". It is not
# imported from landing.py on purpose: a problem in the landing code must
# never break the university pages.
# ---------------------------------------------------------------------------
GUIDE_BASE = "/at/_vorschau/guide/"
SUPPORT_EMAIL = "support@datapublication.nrw"
PAGEDATA = "/at/webcontent/pagedata"


def build_more_information(uni_name: str = "", contact: dict | None = None) -> list[dict]:
    """Entries of the sidebar box: icon, title, text (lines), links.

    A link without href is rendered as a plain label line. contact comes
    from load_uni_contact(); without it the last entry names the
    DataPublication.nrw team only.
    """
    return [
        {
            "icon": f"{PAGEDATA}/icon-policies.svg",
            "title": "Good to know",
            "text": [
                "Nothing is public until a trained reviewer has checked your dataset.",
                "Published datasets get a DOI and stay citable. Changes become new versions.",
                "No personal data: only sufficiently anonymised data can be published.",
            ],
            "links": [
                {"text": "What can I publish here?",
                 "href": f"{GUIDE_BASE}scope-of-datapublication/"},
                {"text": "Which licence fits my data?",
                 "href": f"{GUIDE_BASE}dataset-preparation-workflow/"
                         "choosing-appropriate-licenses-for-your-research-data/"},
            ],
        },
        {
            "icon": f"{PAGEDATA}/icon-research-service.svg",
            "title": "Preparing your data",
            "text": [],
            "links": [
                {"text": "Step-by-step guide",
                 "href": f"{GUIDE_BASE}dataset-preparation-workflow/"},
                {"text": "README template (University of Bonn)",
                 "href": "https://www.forschungsdaten.uni-bonn.de/en/media/"
                         "author_dataset_readmetemplate.txt"},
                {"text": "Naming files (Data Crunch handout)",
                 "href": "https://zenodo.org/records/10275946"},
                {"text": "FAIR spreadsheets (Data Crunch handout)",
                 "href": "https://zenodo.org/records/8380347"},
            ],
        },
        _contact_entry(uni_name, contact),
    ]


def _contact_entry(uni_name: str, contact: dict | None) -> dict:
    team = {"text": SUPPORT_EMAIL, "href": f"mailto:{SUPPORT_EMAIL}"}
    if not contact:
        return {
            "icon": f"{PAGEDATA}/icon-contact.svg",
            "title": "Questions?",
            "text": ["Ask the DataPublication.nrw team at any time, even before you start."],
            "links": [team],
        }
    # The name links to the website if there is one, otherwise it is a label.
    links = [{"text": contact["name"], "href": contact.get("url", "")}]
    if contact.get("email"):
        links.append({"text": contact["email"], "href": f"mailto:{contact['email']}"})
    links += [{"text": "DataPublication.nrw team", "href": ""}, team]
    return {
        "icon": f"{PAGEDATA}/icon-contact.svg",
        "title": f"Your contact at {uni_name}" if uni_name else "Your contact",
        "text": ["Ask at any time, even before you start."],
        "links": links,
    }


def load_uni_contact(uni_dir: Path) -> dict:
    """The university's own research data contact from txt/contact.toml.

    Optional. Keys: name (required), email, url (https only). The file lives
    in the templates repo next to css/ and js/ and is copied to /at/<label>/
    like everything else there, so it is public. A missing, unreadable or
    implausible file only logs a warning; the box then falls back to the
    DataPublication.nrw team.
    """
    path = uni_dir / "txt" / "contact.toml"
    if not path.is_file():
        return {}
    try:
        import tomllib  # Python 3.11+, landing.py relies on it as well

        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except Exception as exc:  # tomllib missing or invalid TOML
        print(f"[WARN] {path}: {exc}", file=sys.stderr)
        return {}
    if not data:  # comments only, e.g. the example copied from layout-adapted
        return {}

    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip()
    url = str(data.get("url", "")).strip()
    if email and (any(c.isspace() for c in email) or email.count("@") != 1):
        print(f"[WARN] {path}: email {email!r} ignored", file=sys.stderr)
        email = ""
    if url and not url.startswith("https://"):
        print(f"[WARN] {path}: url {url!r} ignored, https:// only", file=sys.stderr)
        url = ""
    if not name or not (email or url):
        print(f"[WARN] {path}: needs name plus email or url, ignored", file=sys.stderr)
        return {}
    return {"name": name, "email": email, "url": url}

def project_root_from_file() -> Path:
    return Path(__file__).resolve().parents[2]


def build_env(base_templates_dir: Path, extra_search_paths: list[Path] | None = None) -> Environment:
    loaders = []

    if extra_search_paths:
        loaders.extend(FileSystemLoader(str(p)) for p in extra_search_paths)

    loaders.append(FileSystemLoader(str(base_templates_dir)))
    env = Environment(loader=ChoiceLoader(loaders))

    def inline_svg(rel_path: str, extra_attrs: str = "") -> Markup:
        svg_path = (base_templates_dir / rel_path).resolve()
        svg = svg_path.read_text(encoding="utf-8")
        if extra_attrs:
            svg = svg.replace("<svg", f"<svg {extra_attrs}", 1)
        return Markup(svg)

    env.globals["inline_svg"] = inline_svg
    return env


def read_unis_csv(config_dir: Path) -> pd.DataFrame:
    csv_path = config_dir / "unis.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing CSV: {csv_path}")

    df = pd.read_csv(str(csv_path), delimiter=",", quotechar='"')

    if "label" not in df.columns:
        raise ValueError("unis.csv must contain column: label")

    if "enabled" in df.columns:
        df["enabled"] = df["enabled"].fillna(0).astype(int)
    else:
        df["enabled"] = 1

    df["label"] = df["label"].astype(str).str.strip()
    return df


def pick_uni_template(base_templates_dir: Path, universities_dir: Path, label: str) -> tuple[str, list[Path]]:
    override_dir = universities_dir / label
    override_tpl = override_dir / "subdataverse-homepage-jinja.html"
    default_tpl = base_templates_dir / "subdataverse-homepage-jinja.html"

    if override_tpl.exists():
        return "subdataverse-homepage-jinja.html", [override_dir]

    if default_tpl.exists():
        return "subdataverse-homepage-jinja.html", []

    raise FileNotFoundError(f"Missing default uni template: {default_tpl}")


def collect_items(dataverse_api: DataverseAPI, templater: DataverseTemplate, datasets):
    items = []

    for dataset in datasets:
        global_id_key = None

        if "global_id" in dataset:
            global_id_key = "global_id"
        elif "latestVersion" in dataset:
            alias = dataset["publisher"]
            dataset = dataset["latestVersion"]
            global_id_key = "datasetPersistentId"
            dataset["identifier_of_dataverse"] = alias

        if global_id_key is None or global_id_key not in dataset:
            continue

        imgsrc = dataverse_api.get_dataset_citation_image_src(dataset[global_id_key])
        if not imgsrc:
            imgsrc = FALLBACK_IMAGE_SRC

        items.append(
            templater.get_news_item(
                dataset,
                imgsrc,
                dataverse_api.get_dataverse_url_of(dataset),
                dataverse_api.dataset_statistics(dataset),
            )
        )

    return items


def build_page_data(dataverse_api: DataverseAPI, templater: DataverseTemplate, base_dataverse: str):
    root_info = dataverse_api.get_root_dataverse_info(base_dataverse)
    if not root_info or "data" not in root_info:
        raise RuntimeError(f"Could not load Dataverse info for '{base_dataverse}'.")

    main_dataverse_info = templater.update_hero_section(root_info)

    subdataverses_info = dataverse_api.get_extended_subdataverses_info(base_dataverse)

    root_info["data"]["type"] = "dataverse"
    extended_root = dataverse_api.get_extended_subdataverse_info(root_info["data"])

    dataverse_items = []
    for info in subdataverses_info:
        if info.get("dataverseType") in ("RESEARCHERS", "UNCATEGORIZED", "RESEARCHER"):
            continue
        dataverse_items.append(templater.add_dataverse_item_to_carousel(info))

    # Shuffle the children only. The template treats the FIRST item as the
    # collection itself: the card loop skips it ({% if not loop.first %})
    # and the dropdown labels it as the root. Shuffling after prepending
    # put the root card into the carousel and dropped a random child on
    # every build.
    random.shuffle(dataverse_items)

    if extended_root:
        dataverse_items = [templater.add_dataverse_item_to_carousel(extended_root)] + dataverse_items

    recent_datasets = dataverse_api.parse_datasets_for_carousel(base_dataverse, 8)
    popular_info = dataverse_api.parse_popular_datasets(base_dataverse, 4)

    popular_datasets = popular_info.get("items", [])
    popular_index = {d.get("global_id"): True for d in popular_datasets if d.get("global_id")}
    filtered_recent = [d for d in recent_datasets if d.get("global_id") not in popular_index][:4]

    news_items = collect_items(dataverse_api, templater, filtered_recent)
    popular_items = collect_items(dataverse_api, templater, popular_datasets)

    more_information = build_more_information()

    stat_info = {
        "downloads_lastmonth": popular_info.get("overallcount", 0),
        "published_dataverses": dataverse_api.get_number_of_dataverses(base_dataverse),
        "published_datasets": dataverse_api.get_published_datasets(base_dataverse),
    }

    return {
        "news_items": news_items,
        "popular_items": popular_items,
        "dataverse_items": dataverse_items,
        "more_information": more_information,
        "main_dataverse_info": main_dataverse_info,
        "stat_info": stat_info,
        "page_info": {},
        "map_info": {},
        "stat_labels": {},
    }


def render(env: Environment, template_name: str, context: dict) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = dict(context)
    payload["uni_ctx"] = context
    payload["gen_date"] = now
    payload["dataset_sections"] = [
        {"title": "Popular downloads", "items": context.get("popular_items", [])},
        {"title": "Recent Datasets", "items": context.get("news_items", [])},
    ]
    return env.get_template(template_name).render(payload)


def copy_tree_contents(src_dir: Path, dst_dir: Path) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    for item in src_dir.iterdir():
        dest = dst_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)


def create_overviewjs(csv_path: Path, out_path: Path) -> Path:
    df = pd.read_csv(str(csv_path), delimiter=",", quotechar='"')

    if "label" not in df.columns:
        raise ValueError("create_overviewjs: CSV must contain column 'label'")

    df["label"] = df["label"].astype(str).str.strip()
    if "enabled" in df.columns:
        df["enabled"] = df["enabled"].fillna(0).astype(int)
    else:
        df["enabled"] = 1

    def clean_value(v):
        if pd.isna(v):
            return None
        return v

    overview = {}
    labels_in_order = []

    for _, row in df.iterrows():
        label = str(row.get("label", "")).strip()
        if not label:
            continue

        labels_in_order.append(label)
        row_dict = {col: clean_value(row[col]) for col in df.columns}
        row_dict["label"] = label
        overview[label] = row_dict

    overview_json = json.dumps(overview, ensure_ascii=False, indent=2)
    list_json = json.dumps(labels_in_order, ensure_ascii=False, indent=2)

    js = (
        "/* Auto-generated from config/unis.csv - DO NOT EDIT BY HAND */\n"
        "(function(){\n"
        f"  window.UNIS_OVERVIEW = {overview_json};\n"
        f"  window.UNIS_LIST = {list_json};\n"
        "})();\n"
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(js, encoding="utf-8")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Generate homepage + per-uni pages")
    parser.add_argument("--jinja_template_dir", type=str, required=True, help="Path to templates/base")
    parser.add_argument("--jinja_file", type=str, required=True, help="Index template file")
    parser.add_argument("--server_name", type=str, required=True, help="Server name")
    parser.add_argument("--use_cache", type=str, required=False, help="DataverseAPI cache: True/False")
    parser.add_argument("--base_dataverse", type=str, required=False, help="Alias for root dataverse")
    parser.add_argument("--output_html", type=str, required=True, help="Output HTML file path")
    args = parser.parse_args()

    project_root = project_root_from_file()
    config_dir = project_root / "config"
    templates_root = project_root / "templates"
    base_templates_dir = Path(args.jinja_template_dir).resolve()
    universities_dir = templates_root / "universities"
    assets_dir = templates_root / "assets"

    output_html = Path(args.output_html).resolve()
    at_root = output_html.parent
    output_root = at_root.parent
    at_root.mkdir(parents=True, exist_ok=True)

    server = args.server_name.strip().removeprefix("https://").removeprefix("http://").strip("/")
    base_url = f"https://{server}"
    base_dataverse = args.base_dataverse or ":root"

    dataverse_api = DataverseAPI(base_url, args.use_cache == "True" if args.use_cache else False)
    templater = DataverseTemplate(base_url)

    webcontent_dir = at_root / "webcontent"
    pagedata_out_dir = webcontent_dir / "pagedata"
    pagedata_out_dir.mkdir(parents=True, exist_ok=True)

    if assets_dir.exists():
        copy_tree_contents(assets_dir, webcontent_dir)

    create_overviewjs(config_dir / "unis.csv", webcontent_dir / "js" / "unis_overview.js")

    svg_manip = SVGManipulator(
        template_root=templates_root,
        config=SVGLinkConfig(
            source_svg_rel="assets/pagedata/DP.svg",
            csv_rel_path="../config/unis.csv",
            cache_rel_dir="../output/generated/cache/img",
            out_name="DP.linked.svg",
            server_name=server,
            Arecord=False,
            local_test=True,
        ),
    )
    linked_svg = svg_manip.ensure_linked_svg()

    env_index = build_env(base_templates_dir)
    index_ctx = build_page_data(dataverse_api, templater, base_dataverse=base_dataverse)
    index_html = render(env_index, args.jinja_file, index_ctx)
    output_html.write_text(index_html, encoding="utf-8")

    df_unis = read_unis_csv(config_dir)
    enabled_rows = df_unis[df_unis["enabled"] == 1]

    for _, row in enabled_rows.iterrows():
        label = str(row["label"]).strip()
        if not label:
            continue

        repourl = row.get("repourl")
        if isinstance(repourl, str) and repourl.strip():
            continue

        if not dataverse_api.dataverse_exists(label):
            print(f"[SKIP] Dataverse '{label}' not found (yet).")
            continue

        uni_source_dir = universities_dir / label
        target_dir = at_root / label
        target_dir.mkdir(parents=True, exist_ok=True)

        if uni_source_dir.exists():
            copy_tree_contents(uni_source_dir, target_dir)

        uni_template_name, extra_paths = pick_uni_template(base_templates_dir, universities_dir, label)
        env_uni = build_env(base_templates_dir, extra_search_paths=extra_paths)

        uni_ctx = build_page_data(dataverse_api, templater, base_dataverse=label)

        custom_txt_file = universities_dir / label / "txt" / "main.txt"
        if custom_txt_file.exists() and custom_txt_file.is_file():
            uni_ctx["custom_text"] = custom_txt_file.read_text(encoding="utf-8")

        uni_ctx["uni_label"] = label
        uni_ctx["uni_name"] = str(row.get("Name", "")).strip()
        uni_ctx["more_information"] = build_more_information(
            uni_ctx["uni_name"], load_uni_contact(uni_source_dir)
        )

        logo = row.get("logo")
        if isinstance(logo, str) and logo.strip():
            uni_ctx["logo"] = logo.strip()

        # Optional per-uni favicon. Must tolerate an 11-column CSV (column
        # absent -> default) and an empty cell (NaN, not a str). Empty means
        # the template falls back to the shared instance favicon.
        favicon = row.get("favicon", "")
        uni_ctx["favicon"] = favicon.strip() if isinstance(favicon, str) else ""

        background = str(row.get("background", "")).strip()
        if len(background) < 5:
            background = "/homepage/img/backgrounds/collection_root.jpg"
        uni_ctx["background"] = background

        uni_ctx["css"] = str(row.get("css", "")).strip()
        uni_ctx["js"] = str(row.get("js", "")).strip()
        uni_ctx["homepage"] = str(row.get("homepage", "")).strip()

        shib_entityid = str(row.get("shib_entityid", "")).strip()
        uni_ctx["shib_entityid"] = shib_entityid

        if shib_entityid:
            target = "/shib.xhtml"
            uni_ctx["shib_login_url"] = (
                "/Shibboleth.sso/Login"
                f"?entityID={quote(shib_entityid, safe='')}"
                f"&target={quote(target, safe='/')}"
            )
        else:
            uni_ctx["shib_login_url"] = ""

        uni_html = render(env_uni, uni_template_name, uni_ctx)
        (target_dir / "index.html").write_text(uni_html, encoding="utf-8")

    # New landing page preview. Imported here so that neither an import
    # problem nor bad landing data can break the pages above.
    try:
        try:
            from .landing import render_landing
        except ImportError:
            from landing import render_landing
        render_landing(project_root, at_root, linked_svg, config_dir / "unis.csv")
    except Exception as exc:
        print(f"[LANDING] ERROR: {exc}", file=sys.stderr)
        print("[LANDING] Preview skipped; all other pages were rendered.", file=sys.stderr)

    print(f"Done. Output written to: {output_root}")


if __name__ == "__main__":
    main()
