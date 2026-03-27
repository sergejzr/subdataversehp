from __future__ import annotations

from jinja2 import Environment, FileSystemLoader, ChoiceLoader
from datetime import datetime
import argparse
import random
import shutil
from pathlib import Path
import json
import pandas as pd
from markupsafe import Markup

from DataverseAPI import DataverseAPI
from DataverseTemplate import DataverseTemplate
from SVG_Manipulator import SVGManipulator, SVGLinkConfig


# ----------------------------
# Jinja Environment + inline_svg
# ----------------------------
def build_env(template_dir: Path, extra_search_paths: list[Path] | None = None) -> Environment:
    loaders = []
    if extra_search_paths:
        loaders.extend([FileSystemLoader(str(p)) for p in extra_search_paths])
    loaders.append(FileSystemLoader(str(template_dir)))

    env = Environment(loader=ChoiceLoader(loaders))

    def inline_svg(rel_path: str, extra_attrs: str = "") -> Markup:
        svg_path = (template_dir / rel_path).resolve()
        if template_dir not in svg_path.parents and svg_path != template_dir:
            raise ValueError(f"inline_svg path escapes template dir: {rel_path}")

        svg = svg_path.read_text(encoding="utf-8")
        if extra_attrs:
            svg = svg.replace("<svg", f"<svg {extra_attrs}", 1)
        return Markup(svg)

    env.globals["inline_svg"] = inline_svg
    return env


# ----------------------------
# CSV handling
# ----------------------------
def read_unis_csv(template_dir: Path) -> pd.DataFrame:
    csv_path = template_dir / "conf" / "unis.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing CSV: {csv_path}")

    df = pd.read_csv(str(csv_path), delimiter=",", quotechar='"')
    if "label" not in df.columns:
        raise ValueError("unis.csv must contain column: label")

    if "enabled" in df.columns:
        df["enabled"] = df["enabled"].astype(int)
    else:
        df["enabled"] = 1

    # normalize
    df["label"] = df["label"].astype(str).str.strip()
    return df


def ensure_uni_template_dir(template_dir: Path, label: str) -> Path:
    d = template_dir / "unis" / label
    d.mkdir(parents=True, exist_ok=True)
    return d


def pick_uni_template(template_dir: Path, label: str) -> tuple[str, list[Path]]:
    """
    If homepage_template/unis/{label}/uni-homepage-jinja.html exists -> use it.
    Else use homepage_template/uni-homepage-jinja.html
    """
    override_dir = template_dir / "unis" / label
    override_tpl = override_dir / "uni-homepage-jinja.html"
    default_tpl = template_dir / "uni-homepage-jinja.html"

    if override_tpl.exists():
        return "uni-homepage-jinja.html", [override_dir]
    if default_tpl.exists():
        return "uni-homepage-jinja.html", []
    raise FileNotFoundError(f"Missing default uni template: {default_tpl}")


# ----------------------------
# Dataverse content building
# ----------------------------
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

        imgsrc = dataverse_api.get_dataset_citation_image_src(dataset[global_id_key])
        if not imgsrc:
            imgsrc = "/imglibs/dataset_noicon.jpg"

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
    """
    Builds the same context keys your templates expect, but parameterized
    by base_dataverse (for root page and for per-uni pages).
    """
    root_info = dataverse_api.get_root_dataverse_info(base_dataverse)
    main_dataverse_info = templater.update_hero_section(root_info)

    subdataverses_info = dataverse_api.get_extended_subdataverses_info(base_dataverse)

    root_info["data"]["type"] = "dataverse"
    extended_root = dataverse_api.get_extended_subdataverse_info(root_info["data"])

    dataverse_items = []
    for info in subdataverses_info:
        if info.get("dataverseType") in ("RESEARCHERS", "UNCATEGORIZED", "RESEARCHER"):
            continue
        dataverse_items.append(templater.add_dataverse_item_to_carousel(info))

    random.shuffle(dataverse_items)
    dataverse_items = [templater.add_dataverse_item_to_carousel(extended_root)] + dataverse_items

    recent_datasets = dataverse_api.parse_datasets_for_carousel(base_dataverse, 8)
    popular_info = dataverse_api.parse_popular_datasets(base_dataverse, 4)

    popular_datasets = popular_info.get("items", [])
    popular_index = {d.get("global_id"): True for d in popular_datasets if d.get("global_id")}

    filtered_recent = [d for d in recent_datasets if d.get("global_id") not in popular_index][:4]

    news_items = collect_items(dataverse_api, templater, filtered_recent)
    popular_items = collect_items(dataverse_api, templater, popular_datasets)

    # Your "more_information" block (keep as-is or extend per-uni later)
    more_information = [
        {
            "icon": "/imglibs/logos/webpage/sfd.svg",
            "links": [{"text": "The Research Data Service Center", "href": "https://www.forschungsdaten.uni-bonn.de/"}],
        },
        {
            "icon": "/imglibs/logos/webpage/badge.svg",
            "links": [
                {"text": "Policies & Community Sharing Norms", "href": "https://www.ulb.uni-bonn.de/de/datenschutz"},
                {"text": 'Data Crunch handout "DIY: File naming"', "href": "https://zenodo.org/records/10275946"},
                {"text": 'Data Crunch handout "DIY: FAIR Spreadsheet"', "href": "https://zenodo.org/records/8380347"},
                {"text": "ReadMe file template", "href": "https://www.forschungsdaten.uni-bonn.de/en/media/author_dataset_readmetemplate.txt"},
            ],
        },
        {"icon": "/imglibs/logos/webpage/envelop.svg", "links": [{"text": "Need help? Send us an email!", "href": "mailto:forschungsdaten@uni-bonn.de"}]},
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
    payload["uni_ctx"]=context
    payload["gen_date"] = now
    payload["dataset_sections"] = [
        {"title": "Popular downloads", "items": context.get("popular_items", [])},
        {"title": "Recent Datasets", "items": context.get("news_items", [])},
    ]
    return env.get_template(template_name).render(payload)


# ----------------------------
# IO helpers
# ----------------------------
def copy_pagedata(template_dir: Path, output_root: Path):
    output_root.mkdir(parents=True, exist_ok=True)

    for item in template_dir.iterdir():
        dest = output_root / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)


def ensure_output_structure(output_root: Path):
    (output_root / "at").mkdir(parents=True, exist_ok=True)

# ----------------------------
# create_overviewjs
# ----------------------------
def create_overviewjs(webcontent_out_dir: Path, csv_rel_path: str, out_rel_path: str = "js/unis_overview.js") -> Path:
    """
    Reads CSV located at webcontent_out_dir/csv_rel_path (after copy) and writes JS dictionary to:
      webcontent_out_dir/out_rel_path

    Output JS creates:
      window.UNIS_OVERVIEW = { "<label>": { ...row... }, ... }
      window.UNIS_LIST = ["label1","label2",...]
    """
    csv_path = (webcontent_out_dir / csv_rel_path).resolve()
    if not csv_path.exists():
        raise FileNotFoundError(f"create_overviewjs: CSV not found at {csv_path}")

    df = pd.read_csv(str(csv_path), delimiter=",", quotechar='"')

    if "label" not in df.columns:
        raise ValueError("create_overviewjs: CSV must contain column 'label'")

    # Normalize label + enabled
    df["label"] = df["label"].astype(str).str.strip()
    if "enabled" in df.columns:
        # keep numeric 0/1 for client checks
        df["enabled"] = df["enabled"].fillna(0).astype(int)
    else:
        df["enabled"] = 1

    # Convert NaN -> None for JSON output
    def clean_value(v):
        if pd.isna(v):
            return None
        # keep ints for enabled if possible
        return v

    overview = {}
    labels_in_order = []

    for _, row in df.iterrows():
        label = str(row.get("label", "")).strip()
        if not label:
            continue

        labels_in_order.append(label)

        row_dict = {col: clean_value(row[col]) for col in df.columns}
        # ensure label is clean
        row_dict["label"] = label
        overview[label] = row_dict

    # Make output deterministic
    # (labels order is CSV order; dictionary order in JS will follow insertion order)
    overview_json = json.dumps(overview, ensure_ascii=False, indent=2)
    list_json = json.dumps(labels_in_order, ensure_ascii=False, indent=2)

    js = (
        "/* Auto-generated from conf/unis.csv - DO NOT EDIT BY HAND */\n"
        "(function(){\n"
        f"  window.UNIS_OVERVIEW = {overview_json};\n"
        f"  window.UNIS_LIST = {list_json};\n"
        "})();\n"
    )

    out_path = (webcontent_out_dir / out_rel_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(js, encoding="utf-8")
    return out_path


# ----------------------------
# Main
# ----------------------------
def main():
    parser = argparse.ArgumentParser(description="Generate homepage + per-uni pages")
    parser.add_argument("--jinja_template_dir", type=str, required=True, help="Path to homepage_template")
    parser.add_argument("--jinja_file", type=str, required=True, help="Index template file (e.g. custom-homepage-jinja.html)")
    parser.add_argument("--server_name", type=str, required=True, help="Server name (e.g. bonndata.uni-bonn.de)")
    parser.add_argument("--use_cache", type=str, required=False, help="DataverseAPI cache: True/False")
    parser.add_argument("--base_dataverse", type=str, required=False, help="Alias for root dataverse (default :root)")

    parser.add_argument("--output_html", type=str, required=False, help="outputfile")


    args = parser.parse_args()

    template_dir = Path(args.jinja_template_dir).resolve()
    output_root = template_dir.parent / "homepage_output"
    output_root.mkdir(parents=True, exist_ok=True)
    ensure_output_structure(output_root)

    # Base URL
    server = args.server_name.strip().removeprefix("https://").removeprefix("http://").strip("/")
    base_url = f"https://{server}"

    base_dataverse = args.base_dataverse or ":root"

    # Init Dataverse
    dataverse_api = DataverseAPI(base_url, args.use_cache and args.use_cache == "True")
    templater = DataverseTemplate(base_url)

    # 1) Ensure linked SVG is generated in homepage_template/cache/img
    svg_manip = SVGManipulator(
        template_dir=str(template_dir),
        config=SVGLinkConfig(
            source_svg_rel="webcontent/pagedata/DP.svg",
            csv_rel_path="conf/unis.csv",
            cache_rel_dir="cache/img",
            out_name="DP.linked.svg",
            server_name=server,
            Arecord=False,
            local_test=True
        ),
    )


    # 2) Copy pagedata into output
    copy_pagedata(template_dir/"webcontent", output_root/"at/webcontent")
    create_overviewjs(output_root/"at/webcontent", template_dir/"conf/unis.csv")
    #copy_pagedata(template_dir, output_root, "homepage")
    svg_manip.ensure_linked_svg()
    # 3) Render index.html
    env_index = build_env(template_dir)
    index_ctx = build_page_data(dataverse_api, templater, base_dataverse=base_dataverse)
    index_html = render(env_index, args.jinja_file, index_ctx)
    (output_root / "at/index.html").write_text(index_html, encoding="utf-8")

    # 4) Uni pages
    df_unis = read_unis_csv(template_dir)

    # “jemals enabled”: wir nehmen
    # - alle Labels mit enabled==1 aus CSV
    # - plus alle vorhandenen Override-Ordner homepage_template/unis/*
    # So bleiben einmal angelegte Uni-Strukturen erhalten.
    #ever_enabled = set(df_unis.loc[df_unis["enabled"] == 1, "label"].tolist())
    #existing_override_dirs = set()
    #unis_dir = template_dir / "unis"
    #if unis_dir.exists():
    #    for p in unis_dir.iterdir():
    #        if p.is_dir():
    #            existing_override_dirs.add(p.name.strip())

    #ever_enabled |= existing_override_dirs

    # Create output dirs for ever-enabled (even if not currently rendered)
    #for label in sorted(ever_enabled):
    #    if label:
    #        (output_root / "at" / label).mkdir(parents=True, exist_ok=True)

    # Render ONLY currently enabled==1
    enabled_rows = df_unis[df_unis["enabled"] == 1]

    for _, row in enabled_rows.iterrows():
        label = str(row["label"]).strip()
        if not label:
            continue

        if not pd.isna(row["repourl"]):
            continue

        if not dataverse_api.dataverse_exists(label):
            print(f"[SKIP] Dataverse '{label}' not found (yet).")
            continue

        unis_dir = template_dir / "unis" / label
        #ensure_uni_template_dir(template_dir, label)

        target_dir = output_root / "at" / label

        if unis_dir.exists():
            shutil.copytree(unis_dir, target_dir, dirs_exist_ok=True)
        else:
            target_dir.mkdir(parents=True, exist_ok=True)
            # ensure template override folder exists (so editors can add overrides later)




        uni_template_name, extra_paths = pick_uni_template(template_dir, label)
        env_uni = build_env(template_dir, extra_search_paths=extra_paths)


        # base_dataverse for uni page = label (standard assumption)
        uni_ctx = build_page_data(dataverse_api, templater, base_dataverse=label)

        unis_custom_txt_file = template_dir / "unis" / "txt" / "main.txt"

        if unis_custom_txt_file.exists() and unis_custom_txt_file.is_file():
            uni_ctx["custom_text"] = unis_custom_txt_file.read_text(encoding="utf-8")

        uni_ctx["uni_label"] = label
        uni_ctx["uni_name"] = str(row.get("Name", "")).strip()
        if row["logo"]:
            uni_ctx["logo"] = str(row["logo"]).strip()
        else:
            uni_ctx["logo"] = uni_ctx["main_dataverse_info"]["img_src"]
        uni_ctx["background"] = str(row["background"]).strip()

        if len(uni_ctx["background"])<5:
            uni_ctx["background"]="/homepage/img/backgrounds/collection_root.jpg"

        uni_ctx["css"] = str(row["css"]).strip()
        uni_ctx["js"] = str(row["js"]).strip()



        uni_ctx["homepage"] = str(row["homepage"]).strip()


        uni_html = render(env_uni, uni_template_name, uni_ctx)
        out_file = output_root / "at" / label / "index.html"
        out_file.write_text(uni_html, encoding="utf-8")

    print(f"Done. Output written to: {output_root}")


if __name__ == "__main__":
    main()
