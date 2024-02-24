#! /usr/bin/env python
"""Connector to website (API)"""
from __future__ import annotations

import json
import re
import time
from multiprocessing import Lock
from typing import Optional
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import docker
import requests
from docker.errors import DockerException

import colrev.exceptions as colrev_exceptions
import colrev.ops.built_in.search_sources.doi_org as doi_connector
import colrev.record
from colrev.constants import Fields

if TYPE_CHECKING:  # pragma: no cover
    import colrev.ops.prep

# Note: not implemented as a full search_source
# (including SearchSourcePackageEndpointInterface, packages_endpoints.json)


# pylint: disable=too-few-public-methods


class WebsiteConnector:
    """Connector for the Zotero translator for websites"""

    heuristic_status = colrev.env.package_manager.SearchSourceHeuristicStatus.todo
    docs_link = (
        "https://github.com/CoLRev-Environment/colrev/blob/main/"
        + "colrev/ops/built_in/search_sources/website.py"
    )
    _requests_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36"
    }

    # pylint: disable=unused-argument

    # https://github.com/zotero/translators/
    # https://www.zotero.org/support/dev/translators
    # https://github.com/zotero/translation-server/blob/master/src/formats.js
    IMAGE_NAME = "zotero/translation-server:2.0.4"

    def __init__(
        self,
        *,
        review_manager: colrev.review_manager.ReviewManager,
        settings: Optional[dict] = None,
    ) -> None:
        self.zotero_lock = Lock()
        self.review_manager = review_manager

        if not self.review_manager.in_ci_environment():
            environment_manager = self.review_manager.get_environment_manager()
            environment_manager.build_docker_image(imagename=self.IMAGE_NAME)

    # pylint: disable=colrev-missed-constant-usage
    def _set_url(
        self,
        *,
        record: colrev.record.Record,
        item: dict,
    ) -> None:
        if "url" not in item:
            return
        host = urlparse(item["url"]).hostname
        if host and host.endswith("doi.org"):
            record.data[Fields.DOI] = item["url"].replace("https://doi.org/", "")
            dummy_record = colrev.record.PrepRecord(
                data={Fields.DOI: record.data["doi"]}
            )
            doi_connector.DOIConnector.get_link_from_doi(
                record=dummy_record,
                review_manager=self.review_manager,
            )
            if "https://doi.org/" not in dummy_record.data["url"]:
                record.data[Fields.URL] = dummy_record.data["url"]
        else:
            record.data[Fields.URL] = item["url"]

    def _set_keywords(self, *, record: colrev.record.Record, item: dict) -> None:
        if "tags" not in item or len(item["tags"]) == 0:
            return
        keywords = ", ".join([k["tag"] for k in item["tags"]])
        record.data[Fields.KEYWORDS] = keywords

    def _set_author(self, *, record: colrev.record.Record, item: dict) -> None:
        if "creators" not in item:
            return
        author_str = ""
        for creator in item["creators"]:
            author_str += (
                " and "
                + creator.get("lastName", "")
                + ", "
                + creator.get("firstName", "")
            )
        author_str = author_str[5:]  # drop the first " and "
        record.data[Fields.AUTHOR] = author_str

    # pylint: disable=colrev-missed-constant-usage
    def _set_entrytype(self, *, record: colrev.record.Record, item: dict) -> None:
        record.data[Fields.ENTRYTYPE] = "article"  # default
        if item.get("itemType", "") == "journalArticle":
            record.data[Fields.ENTRYTYPE] = "article"
            if "publicationTitle" in item:
                record.data[Fields.JOURNAL] = item["publicationTitle"]
            if "volume" in item:
                record.data[Fields.VOLUME] = item["volume"]
            if "issue" in item:
                record.data[Fields.NUMBER] = item["issue"]
        if item.get("itemType", "") == "conferencePaper":
            record.data[Fields.ENTRYTYPE] = "inproceedings"
            if "proceedingsTitle" in item:
                record.data[Fields.BOOKTITLE] = item["proceedingsTitle"]

    # pylint: disable=colrev-missed-constant-usage
    def _set_title(self, *, record: colrev.record.Record, item: dict) -> None:
        if "title" not in item:
            return
        record.data[Fields.TITLE] = item["title"]

    # pylint: disable=colrev-missed-constant-usage
    def _set_doi(self, *, record: colrev.record.Record, item: dict) -> None:
        if "doi" not in item:
            return
        record.data[Fields.DOI] = item["doi"].upper()

    def _set_date(self, *, record: colrev.record.Record, item: dict) -> None:
        if "date" not in item:
            return
        year = re.search(r"\d{4}", item["date"])
        if year:
            record.data[Fields.YEAR] = year.group(0)

    # pylint: disable=colrev-missed-constant-usage
    def _set_pages(self, *, record: colrev.record.Record, item: dict) -> None:
        if "pages" not in item:
            return
        record.data[Fields.PAGES] = item["pages"]

    def _update_record(
        self,
        record: colrev.record.Record,
        item: dict,
    ) -> None:
        record.data[Fields.ID] = item["key"]
        self._set_entrytype(record=record, item=item)
        self._set_author(record=record, item=item)
        self._set_title(record=record, item=item)
        self._set_doi(record=record, item=item)
        self._set_date(record=record, item=item)
        self._set_pages(record=record, item=item)
        self._set_url(record=record, item=item)
        self._set_keywords(record=record, item=item)

    def retrieve_md_from_website(self, *, record: colrev.record.Record) -> None:
        """Retrieve the metadata of the associated website (url) based on Zotero"""

        self.zotero_lock.acquire(timeout=60)

        self.start_zotero()
        try:
            content_type_header = {"Content-type": "text/plain"}
            headers = {**self._requests_headers, **content_type_header}
            export = requests.post(
                "http://127.0.0.1:1969/web",
                headers=headers,
                data=record.data[Fields.URL],
                timeout=60,
            )

            if export.status_code != 200:
                self.zotero_lock.release()
                return

            items = json.loads(export.content.decode())
            if len(items) == 0:
                self.zotero_lock.release()
                return
            item = items[0]
            if item["title"] == "Shibboleth Authentication Request":
                self.zotero_lock.release()
                return

            self._update_record(record=record, item=item)

        except (
            json.decoder.JSONDecodeError,
            UnicodeEncodeError,
            requests.exceptions.RequestException,
            KeyError,
        ):
            pass

        self.zotero_lock.release()

    def stop_zotero(self) -> None:
        """Stop the zotero translation service"""

        try:
            client = docker.from_env()
            for container in client.containers.list():
                if self.IMAGE_NAME in str(container.image):
                    container.stop_zotero()
        except DockerException as exc:
            raise colrev_exceptions.ServiceNotAvailableException(
                dep="Zotero (Docker)", detailed_trace=exc
            ) from exc

    def start_zotero(self) -> None:
        """Start the zotero translation service"""

        # pylint: disable=duplicate-code

        try:
            self.stop_zotero()

            client = docker.from_env()
            _ = client.containers.run(
                self.IMAGE_NAME,
                ports={"1969/tcp": ("127.0.0.1", 1969)},
                auto_remove=True,
                detach=True,
            )

            tries = 0
            while tries < 10:
                try:
                    headers = {"Content-type": "text/plain"}
                    requests.post(
                        "http://127.0.0.1:1969/import",
                        headers=headers,
                        data=b"%T Paper title\n\n",
                        timeout=10,
                    )

                except requests.ConnectionError:
                    time.sleep(5)
                    continue
                return

            raise colrev_exceptions.ServiceNotAvailableException(
                dep="Zotero (Docker)", detailed_trace=""
            )

        except DockerException as exc:
            raise colrev_exceptions.ServiceNotAvailableException(
                dep="Zotero (Docker)", detailed_trace=exc
            ) from exc
