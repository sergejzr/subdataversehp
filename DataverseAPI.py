import requests
import os
import time
import json
import base64
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from datetime import datetime, timedelta
import csv
import io
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class DataverseAPI:
    def __init__(self, base_url, use_cache):
        self.base_url = base_url.rstrip("/")
        self.api_url = self.base_url + "/api"
        self.cache_duration = 1800
        self.use_cache = use_cache

        # Store cache inside the checked-out homepage project
        # Example on server:
        # /opt/dvhomepage/homepagebuilder/cache/
        self.cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
        os.makedirs(self.cache_dir, exist_ok=True)

    def _make_request(self, endpoint):
        """Internal method to make a GET request to a given Dataverse API endpoint."""
        cache_file = self._get_cache_filename(endpoint)

        if self.use_cache and self._is_cache_valid(cache_file):
            with open(cache_file, "r", encoding="utf-8") as file:
                return json.load(file)

        url = f"{self.api_url}/{endpoint}"
        try:
            response = requests.get(url, verify=False)
            response.raise_for_status()
            data = response.json()

            if self.use_cache:
                os.makedirs(self.cache_dir, exist_ok=True)
                with open(cache_file, "w", encoding="utf-8") as file:
                    json.dump(data, file)

            return data
        except requests.RequestException as e:
            print(f"Error making request to Dataverse API: {e}")
            return None

    def _make_csv_request(self, endpoint):
        """Internal method to make a CSV GET request to a given Dataverse API endpoint."""
        url = f"{self.api_url}/{endpoint}"
        try:
            response = requests.get(url, verify=False)
            response.raise_for_status()

            file_like_object = io.StringIO(response.text)
            return csv.reader(file_like_object)

        except requests.RequestException as e:
            print(f"Error making request to Dataverse API: {e}")
            return None

    def _get_cache_filename(self, endpoint):
        """Create a Base64 encoded, URL-safe cache file name."""
        encoded_name = base64.urlsafe_b64encode(endpoint.encode()).decode().rstrip("=")
        return os.path.join(self.cache_dir, f"cache_{encoded_name}.json")

    def _is_cache_valid(self, cache_file):
        """Check if the cache file exists and is still valid."""
        if os.path.exists(cache_file):
            file_age = time.time() - os.path.getmtime(cache_file)
            if file_age < self.cache_duration:
                return True
        return False

    def get_root_dataverse_info(self, base_dataverse):
        """Get information about the root Dataverse."""
        return self.get_dataverse_info(base_dataverse)

    def get_subdataverses(self, dataverse_id):
        """Get the list of subdataverses under the root."""
        return self._make_request(f"dataverses/{dataverse_id}/contents")

    def get_dataverse_info(self, dataverse_id):
        """Get information about a specific dataverse by its ID."""
        return self._make_request(f"dataverses/{dataverse_id}")

    def check_image_exists(self, url):
        """
        Check if an image exists at the given URL.

        Parameters:
        url (str): The URL of the image.

        Returns:
        bool: True if the image exists, False otherwise.
        """
        try:
            response = requests.head(url, allow_redirects=True, verify=False)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def get_extended_subdataverse_info(self, subdataverse):
        # Fetch each subdataverse's detailed information
        dataverse_id = subdataverse.get("id")
        dataverse_details = self.get_dataverse_info(dataverse_id)
        backgroundimageurl = "false"

        if dataverse_details and "data" in dataverse_details:
            alias = dataverse_details["data"].get("alias")
            if alias and self.check_image_exists(
                self.base_url + f"/homepage/img/backgrounds/collection_{alias}.jpg"
            ):
                backgroundimageurl = "true"

            dataversersedetails = dataverse_details["data"]
            dataversersedetails["hasbackground"] = backgroundimageurl
            return dataversersedetails

        return False

    def get_extended_subdataverses_info(self, dataverse_id):
        """Retrieve extended information for each subdataverse."""
        extended_info = []

        subdataverses = self.get_subdataverses(dataverse_id)
        if subdataverses and "data" in subdataverses:
            for subdataverse in subdataverses["data"]:
                if "type" in subdataverse and subdataverse["type"] == "dataverse":
                    fullinfo = self.get_extended_subdataverse_info(subdataverse)
                    if fullinfo and fullinfo.get("dataverseType") == "RESEARCHER":
                        continue
                    if fullinfo:
                        extended_info.append(fullinfo)

        return extended_info

    def dataverse_exists(self, alias: str) -> bool:
        info = self.get_dataverse_info(alias)
        return bool(info and info.get("status") == "OK" and "data" in info)

    def parse_datasets_for_carousel(self, base_dataverse, limit):
        """Parse datasets from a JSON response for carousel addition."""
        datasets = []

        json_response = self._make_request(
            f"search?sort=date&order=desc&q=*&per_page={limit}&type=dataset&subtree={base_dataverse}"
        )

        if json_response and json_response.get("status") == "OK" and "items" in json_response.get("data", {}):
            for item in json_response["data"]["items"]:
                datasets.append(item)

        return datasets

    def dataset_info(self, doi):
        endpoint = f'search?q=global_id:"{doi}"&sort=name&order=asc&type=dataset'
        info = self._make_request(endpoint)
        try:
            return info["data"]["items"][0]
        except Exception:
            return None

    def dataset_statistics(self, dataset):
        doi = dataset["global_id"]

        if "downloadsUnique" in dataset:
            downloads = dataset["downloadsUnique"]
        else:
            endpoint = f"datasets/:persistentId/makeDataCount/downloadsUnique?persistentId={doi}"
            downloads = self._make_request(endpoint)

            if downloads and "data" in downloads and "downloadsUnique" in downloads["data"]:
                downloads = downloads["data"]["downloadsUnique"]
            else:
                downloads = 0

        endpoint = f"datasets/:persistentId/makeDataCount/viewsUnique?persistentId={doi}"
        views = self._make_request(endpoint)

        if views and "data" in views and "viewsUnique" in views["data"]:
            views = views["data"]["viewsUnique"]
        else:
            views = 0

        return {"downloadsUnique": downloads, "viewsUnique": views}

    def parse_popular_datasets(self, base_dataverse, limit=4):
        index = self.calculateMetrics(base_dataverse)
        metrics = index["index"]
        sorted_ids = sorted(metrics, key=metrics.get, reverse=True)
        ret = []

        for topid in sorted_ids[:limit]:
            dataset = self.dataset_info(topid)
            if dataset:
                dataset["downloadsUnique"] = metrics[topid]
                ret.append(dataset)

        return {"overallcount": index["overallcount"], "items": ret}

    def calculateMetrics(self, base_dataverse):
        now = datetime.now()
        current_month = now.strftime("%Y-%m")

        delta = timedelta(days=32)
        first_day_of_next_month = datetime(now.year, now.month, 1) + delta
        last_day_of_this_month = first_day_of_next_month - timedelta(days=first_day_of_next_month.day)
        days_until_end_of_month = (last_day_of_this_month - now).days
        _ = days_until_end_of_month  # kept to preserve structure

        if now.month == 1:
            previous_month = f"{now.year - 1}-12"
        else:
            previous_month = f"{now.year}-{now.month - 1:02d}"

        overallcount = 0
        index = {}

        prev = self.uniqueDownloads(base_dataverse, previous_month)
        cur = self.uniqueDownloads(base_dataverse, current_month)

        if prev is None or cur is None:
            return {"index": {}, "overallcount": 0}

        prevcnt = self.sumup2(prev)
        curcnt = self.sumup2(cur)

        return {"index": index, "overallcount": curcnt - prevcnt}

        for csvrespons in [prev, cur]:
            next(csvrespons)

            for row in csvrespons:
                count = 0
                if row[0] in index:
                    count = index[row[0]]

                count = count - int(row[1])
                index[row[0]] = count
                overallcount = overallcount + count

        return {"index": index, "overallcount": cur - prev}

    def sumup2(self, csvrespons):
        next(csvrespons)
        count = 0
        for row in csvrespons:
            count = count + int(row[1])
        return count

    def sumup3(self, csvrespons):
        next(csvrespons)
        count = 0
        for row in csvrespons:
            count = count + int(row[2])
        return count

    def uniqueDownloads(self, base_dataverse, current_month):
        endpoint = f"info/metrics/uniquedownloads/toMonth/{current_month}/?parentAlias={base_dataverse}"
        return self._make_csv_request(endpoint)

    def get_dataset_id_from_doi(self, doi):
        """
        Get the dataset ID using a DOI.

        :param doi: The DOI of the dataset.
        :return: The dataset data if found, otherwise None.
        """
        endpoint = f"datasets/:persistentId/?persistentId={doi}"
        response = self._make_request(endpoint)
        if response and "data" in response:
            return response["data"]
        return None

    def get_server(self):
        """
        Extracts and returns the server (base domain with protocol) from the base URL.

        :return: The server (base domain with protocol) of the base URL.
        """
        parsed_url = urlparse(self.api_url)
        server_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        return server_url

    def get_dataset_citation_image_src(self, persistent_id):
        """
        Get the src attribute of the img within the div with class 'preview-icon-block'
        in the element with id 'datasetCitationActionSummaryBlock' from the dataset page.

        :param persistent_id: The persistent ID of the dataset (e.g., DOI)
        :return: The src of the img if found, or None
        """
        endpoint = f"dataset.xhtml?persistentId={persistent_id}"
        url = f"{self.get_server()}/{endpoint}"

        try:
            response = requests.get(url, verify=False)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            citation_block = soup.find(id="datasetCitationActionSummaryBlock")
            preview_icon_block = citation_block.find("div", class_="preview-icon-block") if citation_block else None

            if preview_icon_block:
                img = preview_icon_block.find("img")
                return img["src"] if img else None

            return None

        except requests.RequestException as e:
            print(f"Error making request to Dataverse API: {e}")
            return None

    def list_files_in_dataset(self, persistent_id):
        """
        List files in a dataset given its persistent ID.

        :param persistent_id: The persistent ID of the dataset (e.g., DOI)
        :return: A list of files in the dataset or None if an error occurs
        """
        endpoint = f"datasets/:persistentId/?persistentId={persistent_id}"
        response = self._make_request(endpoint)

        if response and "data" in response and "latestVersion" in response["data"]:
            files_info = response["data"]["latestVersion"].get("files", [])
            return [
                {
                    "fileName": file["dataFile"]["filename"],
                    "fileId": file["dataFile"]["id"],
                }
                for file in files_info
            ]

        return None

    def get_dataverse_url_of(self, dataset):
        return self.get_server() + "/dataverse/" + dataset["identifier_of_dataverse"]

    def get_usage_statistics(self, object_id, object_type="dataverse"):
        """
        Get usage statistics for a specific dataverse or dataset.

        :param object_id: The ID or persistent identifier of the object to get statistics for.
        :param object_type: The type of the object ('dataverse' or 'dataset').
        :return: A dictionary containing usage statistics.
        """
        metrics_to_fetch = ["views", "downloads"]
        statistics = {}

        for metric in metrics_to_fetch:
            endpoint = f"info/metrics/{object_type}/{object_id}/{metric}/totals"
            stats_response = self._make_request(endpoint)
            if stats_response and "data" in stats_response:
                statistics[metric] = stats_response["data"]

        return statistics

    def get_published_datasets(self, base_dataverse):
        endpoint = "search/?q=*&type=dataset&subtree=" + base_dataverse
        stats_response = self._make_request(endpoint)
        if stats_response and "data" in stats_response:
            return stats_response["data"]["total_count"]
        return 0

    def get_downloads_last_days(self, base_dataverse, dayscnt=30):
        endpoint = f"info/metrics/downloads/pastDays/{dayscnt}?parentAlias=" + base_dataverse
        stats_response = self._make_request(endpoint)
        if stats_response and "data" in stats_response:
            return stats_response["data"]["count"]
        return 0

    def get_number_of_dataverses(self, base_dataverse):
        endpoint = f"info/metrics/dataverses?parentAlias=" + base_dataverse
        stats_response = self._make_request(endpoint)
        if stats_response and "data" in stats_response:
            return stats_response["data"]["count"]
        return 0
