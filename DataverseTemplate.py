from builtins import list
from datetime import datetime
import nltk
import re
#nltk.download()
nltk.download('punkt')
nltk.download('punkt_tab')
import requests
import urllib.parse

from django.utils.safestring import mark_safe
from bs4 import BeautifulSoup

class DataverseTemplate:
    def __init__(self, base_url):
        self.base_url=base_url

    def truncate_string(self, string, length):
        """
        Truncate a string to a specified length and append an ellipsis.

        :param string: The string to truncate.
        :param length: The maximum length of the truncated string.
        :return: Truncated string with ellipsis.
        """
        if len(string) > length:
            return string[:length] + '...'
        else:
            return string


    def extract_first_sentence_nltk(self,text):
        sentences = nltk.sent_tokenize(text)
        return sentences[0].strip() if sentences else ""

    def get_news_item(self, item, image_src, dataverse_url, stats):
        """
        Prepare a news item for rendering with Jinja2.

        :param item: The news item containing necessary data.
        :param image_src: The source URL of the image for the news item.
        :param dataverse_url: URL for the dataverse.
        :return: A dictionary representing the news item.
        """
        title = self.truncate_string(item.get('name', ''), 50)
        date = item.get('published_at', '')
        description = item.get('description', '')
        authors = self.format_authors(item.get('authors', []), 40)
        name_of_dataverse = self.truncate_string(item.get('name_of_dataverse', ''), 10)

        # Convert date string to datetime object and then to desired format
        if date:
            date_object = datetime.strptime(date, "%Y-%m-%dT%H:%M:%SZ")
            formatted_date = date_object.strftime("%d/%m/%Y")
        else:
            formatted_date = ''

        news_item = {
            'url':  item.get('url', ''),
            'image_src': image_src,
            'title': title,
            'full_title':item.get('name', ''),
            'img_alt': title,  # Using title as alt text for the image
            'date': formatted_date,
            'description': self.truncate_string(description, 100),
            'full_description': item.get('description', ''),
            'authors': authors,
            'full_authors': "; ".join(item.get('authors', [])),
            'full_name_of_dataverse': item.get('name_of_dataverse', ''),
            'dataverse_url': dataverse_url,
            'name_of_dataverse':self.truncate_string(item.get('name_of_dataverse', 'bonndata'),15)
        }
        news_item["stats"]=stats
        return news_item
    def check_image_exists(self, url):
        """
        Check if an image exists at the given URL.

        Parameters:
        url (str): The URL of the image.

        Returns:
        bool: True if the image exists, False otherwise.
        """
        try:
            response = requests.head(url, allow_redirects=True)
            return response.status_code == 200
        except requests.RequestException:
            return False
    def add_dataverse_item_to_carousel(self, item):
        """
        Prepare a dataverse item for the carousel for rendering with Jinja2.

        :param item: The dataverse item containing necessary data.
        :return: A dictionary representing the dataverse item.
        """
        title = self.truncate_string(item.get('name', ''), 20)
        theme = item.get('theme')


        if theme:
            image_src = f"/logos/{item.get('id')}/{theme.get('logo')}"
        else:
            image_src = "/imglibs/dataverse_logo.svg"

        img_alt = title
        date = item.get('creationDate', '')
        description = item.get('description', '')

        cleaned = re.sub(r"<.*?>", "", description)

        # shorten to 40 chars
        description = cleaned[:40]

        authors = self.format_authors(item.get('authors', []), 40)

        background_img = "root"
        hasbackground = item.get('hasbackground', "false").lower() == "true"
        if hasbackground:
            background_img = item.get('alias', 'root')
        else:
            background_img = 'root'

        # Convert date string to datetime object and then to desired format
        if date:
            date_object = datetime.strptime(date, "%Y-%m-%dT%H:%M:%SZ")
            formatted_date = date_object.strftime("%d/%m/%Y")
        else:
            formatted_date = ''
        sanitized_description=self.stripHTML(self.sanitize_description(description))
        first_sentence=self.extract_first_sentence_nltk(self.stripHTML(sanitized_description));
        dataverse_item = {
            'id':item.get('id','1'),
            'alias': item.get('alias', 'root'),
            'href': f"/dataverse/{item.get('alias')}",
            'img_src': image_src,
            'img_alt': img_alt,
            'title': title,
            'date': formatted_date,
            'description': self.truncate_string(description, 100),
            'sanitized_description': self.truncate_string(sanitized_description,200),
            'first_sentence': self.truncate_string(first_sentence,500),
            'authors': authors,
            'name_of_dataverse': item.get('name'),
            'hasbackground': item.get('hasbackground','false'),
            'backgroung_img': background_img
        }

        return dataverse_item

    def update_hero_section(self, dataverse_info):
        """
        Prepare the hero section data for rendering with Jinja2.

        :param title: The title for the hero section.
        :param description: The description for the hero section.
        :return: A dictionary with the hero section data.
        """

        description=dataverse_info['data'].get('description','');
        # Assuming you have a method to sanitize the description
        sanitized_desc = self.sanitize_description(description)

        sanitized_desc = self.sanitize_description(description)

        first_sentence = self.extract_first_sentence_nltk(self.stripHTML(sanitized_desc))

        hero_section = {
            'id': dataverse_info['data']['id'],
            'alias': dataverse_info['data']['alias'],
            'name': dataverse_info['data'].get('name', 'Default Title'),
            'description':description,
            'sanitized_description': sanitized_desc,
            'short_description':   self.truncate_string(sanitized_desc,50),
            'first_sentence': self.truncate_string(first_sentence, 500),
        }

        return hero_section

    def sanitize_description(self, description):
        """Sanitize the description to keep only <a> tags."""
        soup = BeautifulSoup(description, 'html.parser')
        for tag in soup.find_all():
            if tag.name != 'a':
                tag.unwrap()
        return str(soup)

    def stripHTML(self, description):
        """Sanitize the description to keep only <a> tags."""
        soup = BeautifulSoup(description, 'html.parser')
        for tag in soup.find_all():
            tag.unwrap()
        return str(soup)

    def format_authors(self, authors, max_length):
        """
        Join the authors' names by ", " not exceeding the max_length.
        The last author will be appended with 'and'.
        If the joined string is too long, include as many names as fit followed by 'et al.'.

        :param authors: List of authors as strings.
        :param max_length: Maximum length of the concatenated string.
        :return: Formatted string of authors.
        """
        if not authors:
            return ''

        if len(authors) == 1:
            # If there's only one author, return the name regardless of max_length
            return authors[0]

        formatted_authors = ''


        for i, author in enumerate(authors):
            if i == len(authors) - 1:  # Last author
                # Check if 'and' can be added without exceeding max_length
                if len(formatted_authors) + len(' and ') + len(author) <= max_length:
                    if formatted_authors.endswith('; '):
                        formatted_authors = formatted_authors.rstrip('; ')
                    if formatted_authors.endswith(', '):
                        formatted_authors = formatted_authors.rstrip(', ')
                    formatted_authors += ' and ' + author
                else:
                    if formatted_authors:  # Check if there's already at least one author added
                        if formatted_authors.endswith('; '):
                            formatted_authors = formatted_authors.rstrip('; ')
                        if formatted_authors.endswith(', '):
                            formatted_authors = formatted_authors.rstrip(', ')
                        formatted_authors += ' et al.'
                    else:
                        # If the first author already exceeds the max_length, we add 'et al.' after their name
                        formatted_authors = f"{author} et al."
                break

            # Check if adding the next author would exceed the max_length
            elif len(formatted_authors) + len(author) + len(', ') > max_length:
                if formatted_authors.endswith('; '):
                    formatted_authors = formatted_authors.rstrip('; ')
                if formatted_authors.endswith(', '):
                    formatted_authors = formatted_authors.rstrip(', ')
                formatted_authors += ' et al.'
                break
            else:
                formatted_authors += author + ', ' if i < len(authors) - 2 else author + '; '

        return formatted_authors


