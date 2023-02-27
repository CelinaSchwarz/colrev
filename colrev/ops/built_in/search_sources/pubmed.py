#! /usr/bin/env python
"""SearchSource: Pubmed"""
from __future__ import annotations

import typing
import xml.etree.ElementTree as ET
from copy import deepcopy
from dataclasses import dataclass
from multiprocessing import Lock
from pathlib import Path
from sqlite3 import OperationalError
from xml.etree.ElementTree import Element

import requests
import zope.interface
from dacite import from_dict
from dataclasses_jsonschema import JsonSchemaMixin

import colrev.env.package_manager
import colrev.exceptions as colrev_exceptions
import colrev.ops.search
import colrev.record
import colrev.ui_cli.cli_colors as colors

# pylint: disable=unused-argument
# pylint: disable=duplicate-code


@zope.interface.implementer(
    colrev.env.package_manager.SearchSourcePackageEndpointInterface
)
@dataclass
class PubMedSearchSource(JsonSchemaMixin):
    """SearchSource for Pubmed"""

    settings_class = colrev.env.package_manager.DefaultSourceSettings
    source_identifier = "pubmedid"
    search_type = colrev.settings.SearchType.DB
    heuristic_status = colrev.env.package_manager.SearchSourceHeuristicStatus.supported
    short_name = "PubMed"
    link = "https://pubmed.ncbi.nlm.nih.gov/"
    __pubmed_md_filename = Path("data/search/md_pubmed.bib")

    def __init__(
        self,
        *,
        source_operation: colrev.operation.Operation,
        settings: dict = None,
    ) -> None:

        if settings:
            # Pubmed as a search_source
            self.search_source = from_dict(
                data_class=self.settings_class, data=settings
            )
        else:
            # Pubmed as an md-prep source
            pubmed_md_source_l = [
                s
                for s in source_operation.review_manager.settings.sources
                if s.filename == self.__pubmed_md_filename
            ]
            if pubmed_md_source_l:
                self.search_source = pubmed_md_source_l[0]
            else:
                self.search_source = colrev.settings.SearchSource(
                    endpoint="colrev_built_in.pubmed",
                    filename=self.__pubmed_md_filename,
                    search_type=colrev.settings.SearchType.OTHER,
                    search_parameters={},
                    load_conversion_package_endpoint={
                        "endpoint": "colrev_built_in.bibtex"
                    },
                    comment="",
                )

            self.pubmed_lock = Lock()

        self.review_manager = source_operation.review_manager
        _, self.email = source_operation.review_manager.get_committer()

    @classmethod
    def heuristic(cls, filename: Path, data: str) -> dict:
        """Source heuristic for Pubmed"""

        result = {"confidence": 0.0}

        # Simple heuristic:
        if "PMID,Title,Authors,Citation,First Author,Journal/Book," in data:
            result["confidence"] = 1.0
            return result
        if "PMID- " in data:
            result["confidence"] = 0.7
            return result

        if "pmid " in data:
            if data.count(" pmid ") > data.count("\n@"):
                result["confidence"] = 1.0

        return result

    def validate_source(
        self,
        search_operation: colrev.ops.search.Search,
        source: colrev.settings.SearchSource,
    ) -> None:
        """Validate the SearchSource (parameters etc.)"""

        search_operation.review_manager.logger.debug(
            f"Validate SearchSource {source.filename}"
        )

        if source.filename.name != self.__pubmed_md_filename.name:

            if "query" not in source.search_parameters:
                raise colrev_exceptions.InvalidQueryException(
                    f"Source missing query search_parameter ({source.filename})"
                )

            # if "query_file" in source.search_parameters:
            # ...

        search_operation.review_manager.logger.debug(
            f"SearchSource {source.filename} validated"
        )

    def check_availability(
        self, *, source_operation: colrev.operation.Operation
    ) -> None:
        """Check status (availability) of the Pubmed API"""

        try:
            # pylint: disable=duplicate-code
            test_rec = {
                "author": "Nazzaro, P and Manzari, M and Merlo, M and Triggiani, R and "
                "Scarano, A and Ciancio, L and Pirrelli, A",
                "title": "Distinct and combined vascular effects of ACE blockade and "
                "HMG-CoA reductase inhibition in hypertensive subjects",
                "ENTRYTYPE": "article",
                "pubmedid": "10024335",
            }
            returned_record_dict = self.__pubmed_query_id(
                pubmed_id=test_rec["pubmedid"],
                timeout=20,
            )

            if returned_record_dict:
                assert returned_record_dict["title"] == test_rec["title"]
                assert returned_record_dict["author"] == test_rec["author"]
            else:
                if not source_operation.force_mode:
                    raise colrev_exceptions.ServiceNotAvailableException("Pubmed")
        except (requests.exceptions.RequestException, IndexError) as exc:
            print(exc)
            if not source_operation.force_mode:
                raise colrev_exceptions.ServiceNotAvailableException("Pubmed") from exc

    @classmethod
    def __pubmed_xml_to_record(cls, *, root: Element) -> dict:

        # pylint: disable=too-many-branches
        # pylint: disable=too-many-locals
        # pylint: disable=too-many-statements
        # pylint: disable=too-many-nested-blocks

        retrieved_record_dict: dict = {"ENTRYTYPE": "misc"}

        pubmed_article = root.find("PubmedArticle")
        item = None
        if pubmed_article is not None:
            item = pubmed_article.find("MedlineCitation")
        if item is not None:
            article_node = item.find("Article")
        else:
            return {}

        authors_string = ""
        if article_node is not None:
            author_list_node = article_node.find("AuthorList")
            if author_list_node is not None:
                author_nodes = author_list_node.findall("Author")
                if author_nodes is not None:
                    for author_node in author_nodes:
                        if author_node is not None:
                            author_last_name_node = author_node.find("LastName")
                            if author_last_name_node is not None:
                                if author_last_name_node.text is not None:
                                    authors_string += author_last_name_node.text
                            author_fore_name_node = author_node.find("ForeName")
                            if author_fore_name_node is not None:
                                if author_fore_name_node.text is not None:
                                    authors_string += ", "
                                    authors_string += author_fore_name_node.text
                            authors_string += " and "
        authors_string = authors_string.rstrip(" and ")
        retrieved_record_dict.update(author=authors_string)

        if article_node is not None:
            title_node = article_node.find("ArticleTitle")
            if title_node is not None:
                if title_node.text is not None:
                    retrieved_record_dict.update(title=title_node.text.rstrip("."))

        if article_node is not None:
            journal_node = article_node.find("Journal")
            if journal_node is not None:
                journal_name_node = journal_node.find("ISOAbbreviation")
                if journal_name_node is not None:
                    if journal_name_node.text is not None:
                        retrieved_record_dict.update(journal=journal_name_node.text)
                        retrieved_record_dict.update(ENTRYTYPE="article")
                journal_issue_node = journal_node.find("JournalIssue")
                if journal_issue_node is not None:
                    journal_volume_node = journal_issue_node.find("Volume")
                    if journal_volume_node is not None:
                        if journal_volume_node.text is not None:
                            retrieved_record_dict.update(
                                volume=journal_volume_node.text
                            )
                    journal_number_node = journal_issue_node.find("Issue")
                    if journal_number_node is not None:
                        if journal_number_node.text is not None:
                            retrieved_record_dict.update(
                                number=journal_number_node.text
                            )

                    pubdate_node = journal_issue_node.find("PubDate")
                    if pubdate_node is not None:
                        if pubdate_node.text is not None:
                            retrieved_record_dict.update(year=pubdate_node.text)

        if article_node is not None:
            abstract_node = article_node.find("Abstract")
            if abstract_node is not None:
                if abstract_node.text is not None:
                    retrieved_record_dict.update(abstract=abstract_node.text)

        if pubmed_article is not None:
            pubmed_data_node = pubmed_article.find("PubmedData")
            if pubmed_data_node is not None:
                article_id_node = pubmed_data_node.find("ArticleIdList")
                if article_id_node is not None:
                    for article_id_node_item in article_id_node:
                        id_type = article_id_node_item.attrib.get("IdType")
                        id_text = article_id_node_item.text
                        if id_type is not None and id_text is not None:
                            if "pubmed" == id_type:
                                id_type = "pubmedid"
                            if "doi" == id_type:
                                id_text = id_text.upper()
                            retrieved_record_dict[id_type] = id_text

        return retrieved_record_dict

    def __get_pubmed_ids(self, query: str, retstart: int) -> typing.List[str]:

        headers = {"user-agent": f"{__name__} (mailto:{self.email})"}
        session = self.review_manager.get_cached_session()

        ret = session.request(
            "GET", query + f"&retstart={retstart}", headers=headers, timeout=30
        )

        ret.raise_for_status()
        if ret.status_code != 200:
            # review_manager.logger.debug(
            #     f"crossref_query failed with status {ret.status_code}"
            # )
            return []

        root = ET.fromstring(ret.text)
        return [
            x.text
            for x_el in root.findall("IdList")
            for x in x_el
            if x.text is not None
        ]

    def __pubmed_query_id(
        self,
        *,
        pubmed_id: str,
        timeout: int = 10,
    ) -> dict:
        """Retrieve records from Pubmed based on a query"""

        try:

            database = "pubmed"
            url = (
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
                + f"db={database}&id={pubmed_id}&rettype=xml&retmode=text"
            )

            headers = {"user-agent": f"{__name__} (mailto:{self.email})"}
            session = self.review_manager.get_cached_session()

            # review_manager.logger.debug(url)
            ret = session.request("GET", url, headers=headers, timeout=timeout)
            ret.raise_for_status()
            if ret.status_code != 200:
                # review_manager.logger.debug(
                #     f"crossref_query failed with status {ret.status_code}"
                # )
                return {}

            root = ET.fromstring(ret.text)
            retrieved_record = self.__pubmed_xml_to_record(root=root)
            if not retrieved_record:
                return {}
        except requests.exceptions.RequestException:
            return {}
        # pylint: disable=duplicate-code
        except OperationalError as exc:
            raise colrev_exceptions.ServiceNotAvailableException(
                "sqlite, required for requests CachedSession "
                "(possibly caused by concurrent operations)"
            ) from exc

        return retrieved_record

    def __get_masterdata_record(
        self,
        prep_operation: colrev.ops.prep.Prep,
        record: colrev.record.Record,
        timeout: int,
        safe_feed: bool,
    ) -> colrev.record.Record:

        try:

            retrieved_record_dict = self.__pubmed_query_id(
                pubmed_id=record.data["pubmedid"],
                timeout=timeout,
            )

            retries = 0
            while (
                not retrieved_record_dict
                and retries < prep_operation.max_retries_on_error
            ):
                retries += 1

                retrieved_record_dict = self.__pubmed_query_id(
                    pubmed_id=record.data["pubmedid"],
                    timeout=timeout,
                )

            if not retrieved_record_dict:
                raise colrev_exceptions.RecordNotFoundInPrepSourceException()

            retrieved_record = colrev.record.Record(data=retrieved_record_dict)

            similarity = colrev.record.PrepRecord.get_retrieval_similarity(
                record_original=record, retrieved_record_original=retrieved_record
            )
            # prep_operation.review_manager.logger.debug("Found matching record")
            # prep_operation.review_manager.logger.debug(
            #     f"crossref similarity: {similarity} "
            #     f"(>{prep_operation.retrieval_similarity})"
            # )
            self.review_manager.logger.debug(
                f"pubmed similarity: {similarity} "
                f"(<{prep_operation.retrieval_similarity})"
            )

            try:
                self.pubmed_lock.acquire(timeout=60)

                # Note : need to reload file because the object is not shared between processes
                pubmed_feed = self.search_source.get_feed(
                    review_manager=self.review_manager,
                    source_identifier=self.source_identifier,
                    update_only=False,
                )

                pubmed_feed.set_id(record_dict=retrieved_record.data)
                pubmed_feed.add_record(record=retrieved_record)

                record.merge(
                    merging_record=retrieved_record,
                    default_source=retrieved_record.data["colrev_origin"][0],
                )

                record.set_masterdata_complete(
                    source=retrieved_record.data["colrev_origin"][0]
                )
                record.set_status(target_state=colrev.record.RecordState.md_prepared)
                if safe_feed:
                    pubmed_feed.save_feed_file()
                self.pubmed_lock.release()
                return record
            except (
                colrev_exceptions.InvalidMerge,
                colrev_exceptions.NotFeedIdentifiableException,
            ):
                self.pubmed_lock.release()
                return record

        except (
            requests.exceptions.RequestException,
            OSError,
            IndexError,
            colrev_exceptions.RecordNotFoundInPrepSourceException,
        ):
            pass
        return record

    def get_masterdata(
        self,
        *,
        prep_operation: colrev.ops.prep.Prep,
        record: colrev.record.Record,
        safe_feed: bool = True,
        timeout: int = 10,
    ) -> colrev.record.Record:
        """Retrieve masterdata from Pubmed based on similarity with the record provided"""

        # To test the metadata provided for a particular pubmed-id use:
        # https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=10075143&rettype=xml&retmode=text

        if len(record.data.get("title", "")) < 35 and "pubmedid" not in record.data:
            return record

        # at this point, we coujld validate metadata
        # if "pubmedid" not in record.data:
        #    record = self.__check_doi_masterdata(record=record)

        # remove the following if we match basd on similarity
        if "pubmedid" not in record.data:
            return record

        record = self.__get_masterdata_record(
            prep_operation=prep_operation,
            record=record,
            timeout=timeout,
            safe_feed=safe_feed,
        )

        return record

    def __get_pubmed_query_return(self) -> typing.Iterator[dict]:
        params = self.search_source.search_parameters

        retstart = 0
        while True:

            pubmed_ids = self.__get_pubmed_ids(query=params["query"], retstart=retstart)
            if not pubmed_ids:
                break
            for pubmed_id in pubmed_ids:
                yield self.__pubmed_query_id(pubmed_id=pubmed_id)

            retstart += 20
            # input(pubmed_ids)

    def __run_parameter_search(
        self,
        *,
        search_operation: colrev.ops.search.Search,
        pubmed_feed: colrev.ops.search.GeneralOriginFeed,
        rerun: bool,
    ) -> None:

        # pylint: disable=too-many-branches

        if rerun:
            search_operation.review_manager.logger.info(
                "Performing a search of the full history (may take time)"
            )

        records = search_operation.review_manager.dataset.load_records_dict()
        nr_retrieved, nr_changed = 0, 0

        try:

            for record_dict in self.__get_pubmed_query_return():
                # Note : discard "empty" records
                if "" == record_dict.get("author", "") and "" == record_dict.get(
                    "title", ""
                ):
                    continue
                try:

                    pubmed_feed.set_id(record_dict=record_dict)
                except colrev_exceptions.NotFeedIdentifiableException:
                    continue

                prev_record_dict_version = {}
                if record_dict["ID"] in pubmed_feed.feed_records:
                    prev_record_dict_version = deepcopy(
                        pubmed_feed.feed_records[record_dict["ID"]]
                    )

                prep_record = colrev.record.PrepRecord(data=record_dict)

                if "colrev_data_provenance" in prep_record.data:
                    del prep_record.data["colrev_data_provenance"]

                added = pubmed_feed.add_record(record=prep_record)

                if added:
                    search_operation.review_manager.logger.info(
                        " retrieve pubmed-id=" + prep_record.data["pubmedid"]
                    )
                    nr_retrieved += 1
                else:
                    changed = search_operation.update_existing_record(
                        records=records,
                        record_dict=prep_record.data,
                        prev_record_dict_version=prev_record_dict_version,
                        source=self.search_source,
                        update_time_variant_fields=rerun,
                    )
                    if changed:
                        nr_changed += 1

                # Note : only retrieve/update the latest deposits (unless in rerun mode)
                if not added and not rerun:
                    # problem: some publishers don't necessarily
                    # deposit papers chronologically
                    break

            if nr_retrieved > 0:
                search_operation.review_manager.logger.info(
                    f"{colors.GREEN}Retrieved {nr_retrieved} records{colors.END}"
                )
            else:
                search_operation.review_manager.logger.info(
                    f"{colors.GREEN}No additional records retrieved{colors.END}"
                )

            if nr_changed > 0:
                self.review_manager.logger.info(
                    f"{colors.GREEN}Updated {nr_changed} records{colors.END}"
                )
            else:
                if records:
                    self.review_manager.logger.info(
                        f"{colors.GREEN}Records (data/records.bib) up-to-date{colors.END}"
                    )

            pubmed_feed.save_feed_file()
            search_operation.review_manager.dataset.save_records_dict(records=records)
            search_operation.review_manager.dataset.add_record_changes()

        except (requests.exceptions.JSONDecodeError) as exc:
            # watch github issue:
            # https://github.com/fabiobatalha/crossrefapi/issues/46
            if "504 Gateway Time-out" in str(exc):
                raise colrev_exceptions.ServiceNotAvailableException(
                    "Crossref (check https://status.crossref.org/)"
                )
            raise colrev_exceptions.ServiceNotAvailableException(
                f"Crossref (check https://status.crossref.org/) ({exc})"
            )

    def __run_md_search_update(
        self,
        *,
        search_operation: colrev.ops.search.Search,
        pubmed_feed: colrev.ops.search.GeneralOriginFeed,
    ) -> None:

        records = search_operation.review_manager.dataset.load_records_dict()

        nr_changed = 0
        for feed_record_dict in pubmed_feed.feed_records.values():
            feed_record = colrev.record.Record(data=feed_record_dict)

            try:
                retrieved_record = self.__pubmed_query_id(
                    pubmed_id=feed_record_dict["pubmedid"]
                )

                if retrieved_record["pubmedid"] != feed_record.data["pubmedid"]:
                    continue

                pubmed_feed.set_id(record_dict=retrieved_record)
            except (
                colrev_exceptions.RecordNotFoundInPrepSourceException,
                colrev_exceptions.NotFeedIdentifiableException,
            ):
                continue

            prev_record_dict_version = {}
            if retrieved_record["ID"] in pubmed_feed.feed_records:
                prev_record_dict_version = pubmed_feed.feed_records[
                    retrieved_record["ID"]
                ]

            pubmed_feed.add_record(record=colrev.record.Record(data=retrieved_record))

            changed = search_operation.update_existing_record(
                records=records,
                record_dict=retrieved_record,
                prev_record_dict_version=prev_record_dict_version,
                source=self.search_source,
                update_time_variant_fields=True,
            )
            if changed:
                nr_changed += 1

        if nr_changed > 0:
            self.review_manager.logger.info(
                f"{colors.GREEN}Updated {nr_changed} "
                f"records based on Pubmed{colors.END}"
            )
        else:
            if records:
                self.review_manager.logger.info(
                    f"{colors.GREEN}Records (data/records.bib) up-to-date with Pubmed{colors.END}"
                )

        pubmed_feed.save_feed_file()
        search_operation.review_manager.dataset.save_records_dict(records=records)
        search_operation.review_manager.dataset.add_record_changes()

    def run_search(
        self, search_operation: colrev.ops.search.Search, rerun: bool
    ) -> None:
        """Run a search of Pubmed"""

        pubmed_feed = self.search_source.get_feed(
            review_manager=search_operation.review_manager,
            source_identifier=self.source_identifier,
            update_only=(not rerun),
        )

        if self.search_source.is_md_source() or self.search_source.is_quasi_md_source():
            self.__run_md_search_update(
                search_operation=search_operation,
                pubmed_feed=pubmed_feed,
            )

        else:
            self.__run_parameter_search(
                search_operation=search_operation,
                pubmed_feed=pubmed_feed,
                rerun=rerun,
            )

    def load_fixes(
        self,
        load_operation: colrev.ops.load.Load,
        source: colrev.settings.SearchSource,
        records: typing.Dict,
    ) -> dict:
        """Load fixes for Pubmed"""

        return records

    def prepare(
        self, record: colrev.record.Record, source: colrev.settings.SearchSource
    ) -> colrev.record.Record:
        """Source-specific preparation for Pubmed"""

        if "first_author" in record.data:
            record.remove_field(key="first_author")
        if "journal/book" in record.data:
            record.rename_field(key="journal/book", new_key="journal")
        if "UNKNOWN" == record.data.get("author") and "authors" in record.data:
            record.remove_field(key="author")
            record.rename_field(key="authors", new_key="author")

        if "UNKNOWN" == record.data.get("year"):
            record.remove_field(key="year")
            if "publication_year" in record.data:
                record.rename_field(key="publication_year", new_key="year")

        if "author" in record.data:
            record.data["author"] = colrev.record.PrepRecord.format_author_field(
                input_string=record.data["author"]
            )

        # TBD: how to distinguish other types?
        record.change_entrytype(new_entrytype="article")
        record.import_provenance(review_manager=self.review_manager)

        return record


if __name__ == "__main__":
    pass
