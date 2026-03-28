from __future__ import annotations

import argparse
import json
import random
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd
from jinja2 import ChoiceLoader, Environment, FileSystemLoader
from markupsafe import Markup

try:
    from .dataverse_api import DataverseAPI
    from .dataverse_template import DataverseTemplate
    from .svg_manipulator import SVGLinkConfig, SVGManipulator
except ImportError:
    from dataverse_api import DataverseAPI
    from dataverse_template import DataverseTemplate
    from svg_manipulator import SVGLinkConfig, SVGManipulator


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
            imgsrc = "/at/webcontent/pagedata/dp-logo.svg"

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

    if extended_root:
        dataverse_items = [templater.add_dataverse_item_to_carousel(extended_root)] + dataverse_items

    random.shuffle(dataverse_items)

    recent_datasets = dataverse_api.parse_datasets_for_carousel(base_dataverse, 8)
    popular_info = dataverse_api.parse_popular_datasets(base_dataverse, 4)

    popular_datasets = popular_info.get("items", [])
    popular_index = {d.get("global_id"): True for d in popular_datasets if d.get("global_id")}
    filtered_recent = [d for d in recent_datasets if d.get("global_id") not in popular_index][:4]

    news_items = collect_items(dataverse_api, templater, filtered_recent)
    popular_items = collect_items(dataverse_api, templater, popular_datasets)

    more_information = [
        {
            "icon": "/at/webcontent/pagedata/dp-logo.svg",
            "links": [{"text": "The Research Data Service Center", "href": "https://www.forschungsdaten.uni-bonn.de/"}],
        },
        {
            "icon": "/at/webcontent/pagedata/dp-logo.svg",
            "links": [
                {"text": "Policies & Community Sharing Norms", "href": "https://www.ulb.uni-bonn.de/de/datenschutz"},
                {"text": 'Data Crunch handout "DIY: File naming"', "href": "https://zenodo.org/records/10275946"},
                {"text": 'Data Crunch handout "DIY: FAIR Spreadsheet"', "href": "https://zenodo.org/records/8380347"},
                {"text": "ReadMe file template", "href": "https://www.forschungsdaten.uni-bonn.de/en/media/author_dataset_readmetemplate.txt"},
            ],
        },
        {
            "icon": "/at/webcontent/pagedata/dp-logo.svg",
            "links": [{"text": "Need help? Send us an email!", "href": "mailto:forschungsdaten@uni-bonn.de"}],
        },
    ]

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
    svg_manip.ensure_linked_svg()

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

        logo = row.get("logo")
        if isinstance(logo, str) and logo.strip():
            uni_ctx["logo"] = logo.strip()

        background = str(row.get("background", "")).strip()
        if len(background) < 5:
            background = "/at/webcontent/pagedata/dh.png"
        uni_ctx["background"] = background

        uni_ctx["css"] = str(row.get("css", "")).strip()
        uni_ctx["js"] = str(row.get("js", "")).strip()
        uni_ctx["homepage"] = str(row.get("homepage", "")).strip()

        uni_html = render(env_uni, uni_template_name, uni_ctx)
        (target_dir / "index.html").write_text(uni_html, encoding="utf-8")

    print(f"Done. Output written to: {output_root}")


if __name__ == "__main__":
    main()
