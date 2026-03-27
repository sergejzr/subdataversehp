from __future__ import annotations

from datetime import datetime
import re

import requests
from bs4 import BeautifulSoup


class DataverseTemplate:
    def __init__(self, base_url):
        self.base_url = base_url

    def truncate_string(self, string, length):
        string = string or ""
        if len(string) > length:
            return string[:length] + "..."
        return string

    def extract_first_sentence(self, text):
        text = (text or "").strip()
        if not text:
            return ""

        match = re.search(r"(.+?[.!?])(?:\s|$)", text, flags=re.DOTALL)
        if match:
            return match.group(1).strip()
        return text

    def get_news_item(self, item, image_src, dataverse_url, stats):
        title = self.truncate_string(item.get("name", ""), 50)
        date = item.get("published_at", "")
        description = item.get("description", "")
        authors = self.format_authors(item.get("authors", []), 40)

        if date:
            date_object = datetime.strptime(date, "%Y-%m-%dT%H:%M:%SZ")
            formatted_date = date_object.strftime("%d/%m/%Y")
        else:
            formatted_date = ""

        return {
            "url": item.get("url", ""),
            "image_src": image_src,
            "title": title,
            "full_title": item.get("name", ""),
            "img_alt": title,
            "date": formatted_date,
            "description": self.truncate_string(description, 100),
            "full_description": item.get("description", ""),
            "authors": authors,
            "full_authors": "; ".join(item.get("authors", [])),
            "full_name_of_dataverse": item.get("name_of_dataverse", ""),
            "dataverse_url": dataverse_url,
            "name_of_dataverse": self.truncate_string(item.get("name_of_dataverse", "bonndata"), 15),
            "stats": stats,
        }

    def check_image_exists(self, url):
        try:
            response = requests.head(url, allow_redirects=True, timeout=10)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def add_dataverse_item_to_carousel(self, item):
        title = self.truncate_string(item.get("name", ""), 20)
        theme = item.get("theme")

        if theme:
            image_src = f"/logos/{item.get('id')}/{theme.get('logo')}"
        else:
            image_src = "/at/webcontent/pagedata/dp-logo.svg"

        date = item.get("creationDate", "")
        raw_description = item.get("description", "")
        cleaned = re.sub(r"<.*?>", "", raw_description)
        description = cleaned[:40]
        authors = self.format_authors(item.get("authors", []), 40)

        hasbackground = str(item.get("hasbackground", "false")).lower() == "true"
        background_img = item.get("alias", "root") if hasbackground else "root"

        if date:
            date_object = datetime.strptime(date, "%Y-%m-%dT%H:%M:%SZ")
            formatted_date = date_object.strftime("%d/%m/%Y")
        else:
            formatted_date = ""

        sanitized_description = self.stripHTML(self.sanitize_description(description))
        first_sentence = self.extract_first_sentence(self.stripHTML(sanitized_description))

        return {
            "id": item.get("id", "1"),
            "alias": item.get("alias", "root"),
            "href": f"/dataverse/{item.get('alias')}",
            "img_src": image_src,
            "img_alt": title,
            "title": title,
            "date": formatted_date,
            "description": self.truncate_string(description, 100),
            "sanitized_description": self.truncate_string(sanitized_description, 200),
            "first_sentence": self.truncate_string(first_sentence, 500),
            "authors": authors,
            "name_of_dataverse": item.get("name"),
            "hasbackground": item.get("hasbackground", "false"),
            "background_img": background_img,
        }

    def update_hero_section(self, dataverse_info):
        description = dataverse_info["data"].get("description", "")
        sanitized_desc = self.sanitize_description(description)
        first_sentence = self.extract_first_sentence(self.stripHTML(sanitized_desc))

        return {
            "id": dataverse_info["data"]["id"],
            "alias": dataverse_info["data"]["alias"],
            "name": dataverse_info["data"].get("name", "Default Title"),
            "description": description,
            "sanitized_description": sanitized_desc,
            "short_description": self.truncate_string(sanitized_desc, 50),
            "first_sentence": self.truncate_string(first_sentence, 500),
        }

    def sanitize_description(self, description):
        soup = BeautifulSoup(description or "", "html.parser")
        for tag in soup.find_all():
            if tag.name != "a":
                tag.unwrap()
        return str(soup)

    def stripHTML(self, description):
        soup = BeautifulSoup(description or "", "html.parser")
        for tag in soup.find_all():
            tag.unwrap()
        return str(soup)

    def format_authors(self, authors, max_length):
        if not authors:
            return ""

        if len(authors) == 1:
            return authors[0]

        formatted_authors = ""

        for i, author in enumerate(authors):
            if i == len(authors) - 1:
                if len(formatted_authors) + len(" and ") + len(author) <= max_length:
                    if formatted_authors.endswith("; "):
                        formatted_authors = formatted_authors.rstrip("; ")
                    if formatted_authors.endswith(", "):
                        formatted_authors = formatted_authors.rstrip(", ")
                    formatted_authors += " and " + author
                else:
                    if formatted_authors:
                        if formatted_authors.endswith("; "):
                            formatted_authors = formatted_authors.rstrip("; ")
                        if formatted_authors.endswith(", "):
                            formatted_authors = formatted_authors.rstrip(", ")
                        formatted_authors += " et al."
                    else:
                        formatted_authors = f"{author} et al."
                break

            elif len(formatted_authors) + len(author) + len(", ") > max_length:
                if formatted_authors.endswith("; "):
                    formatted_authors = formatted_authors.rstrip("; ")
                if formatted_authors.endswith(", "):
                    formatted_authors = formatted_authors.rstrip(", ")
                formatted_authors += " et al."
                break
            else:
                formatted_authors += author + ", " if i < len(authors) - 2 else author + "; "

        return formatted_authors
