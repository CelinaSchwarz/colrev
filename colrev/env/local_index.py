#! /usr/bin/env python
"""Indexing and retrieving records locally."""
from __future__ import annotations

import collections
import hashlib
import os
import sqlite3
import typing
from copy import deepcopy
from datetime import timedelta
from multiprocessing import Lock
from pathlib import Path
from threading import Timer

import requests_cache
from pybtex.database.input import bibtex
from thefuzz import fuzz
from tqdm import tqdm

import colrev.dataset
import colrev.env.environment_manager
import colrev.env.tei_parser
import colrev.exceptions as colrev_exceptions
import colrev.operation
import colrev.record

# import binascii

# pylint: disable=too-many-lines


class LocalIndex:
    """The LocalIndex implements indexing and retrieval of records across projects"""

    global_keys = ["doi", "dblp_key", "colrev_pdf_id", "url", "colrev_id"]
    max_len_sha256 = 2**256
    request_timeout = 90

    local_environment_path = Path.home().joinpath("colrev")
    SQLITE_PATH = str(local_environment_path / Path("sqlite_index.db"))

    teiind_path = local_environment_path / Path(".tei_index/")
    annotators_path = local_environment_path / Path("annotators")

    # Note : records are indexed by id = hash(colrev_id)
    # to ensure that the indexing-ids do not exceed limits
    # such as the opensearch limit of 512 bytes.
    # This enables efficient retrieval based on id=hash(colrev_id)
    # but also search-based retrieval using only colrev_ids

    RECORD_INDEX = "record_index"
    TOC_INDEX = "toc_index"
    # AUTHOR_INDEX = "author_index"
    # AUTHOR_RECORD_INDEX = "author_record_index"
    # CITATIONS_INDEX = "citations_index"

    RECORDS_INDEX_KEYS = [
        "id",
        "colrev_id",
        "title",
        "abstract",
        "file",
        "tei",
        "fulltext",
        "url",
        "doi",
        "dblp_key",
        "corlev_pdf_id",
        "bibtex",
        # "curation_ID"
    ]

    # Note: we need the local_curated_metadata field for is_duplicate()

    def __init__(
        self,
        *,
        verbose_mode: bool = False,
    ) -> None:

        self.verbose_mode = verbose_mode
        self.environment_manager = colrev.env.environment_manager.EnvironmentManager()
        self.__index_tei = True
        self.__sqlite_connection = sqlite3.connect(self.SQLITE_PATH)
        self.__thread_lock = Lock()

    def __dict_factory(self, cursor: sqlite3.Cursor, row: dict) -> dict:
        ret_dict = {}
        for idx, col in enumerate(cursor.description):
            ret_dict[col[0]] = row[idx]
        return ret_dict

    def __get_record_hash(self, *, record_dict: dict) -> str:
        # Note : may raise NotEnoughDataToIdentifyException
        string_to_hash = colrev.record.Record(data=record_dict).create_colrev_id()
        return hashlib.sha256(string_to_hash.encode("utf-8")).hexdigest()

    # def __increment_hash(self, *, paper_hash: str) -> str:
    #     plaintext = binascii.unhexlify(paper_hash)
    #     # also, we'll want to know our length later on
    #     plaintext_length = len(plaintext)
    #     plaintext_number = int.from_bytes(plaintext, "big")

    #     # recommendation: do not increment by 1
    #     plaintext_number += 10
    #     plaintext_number = plaintext_number % self.max_len_sha256

    #     new_plaintext = plaintext_number.to_bytes(plaintext_length, "big")
    #     new_hex = binascii.hexlify(new_plaintext)
    #     # print(new_hex.decode("utf-8"))

    #     return new_hex.decode("utf-8")

    def __get_tei_index_file(self, *, paper_hash: str) -> Path:
        return self.teiind_path / Path(f"{paper_hash[:2]}/{paper_hash[2:]}.tei.xml")

    # def __index_author(
    #     self, tei: colrev.env.tei_parser.TEIParser, record_dict: dict
    # ) -> None:
    #     print("index_author currently not implemented")
    # author_details = tei.get_author_details()
    # # Iterate over curated metadata and enrich it based on TEI (may vary in quality)
    # for author in record_dict.get("author", "").split(" and "):
    #     if "," not in author:
    #         continue
    #     author_dict = {}
    #     author_dict["surname"] = author.split(", ")[0]
    #     author_dict["forename"] = author.split(", ")[1]
    #     for author_detail in author_details:
    #         if author_dict["surname"] == author_detail["surname"]:
    #             # Add complementary details
    #             author_dict = {**author_dict, **author_detail}
    #     self.open_search.index(index=self.AUTHOR_INDEX, body=author_dict)

    def __index_tei_document(self, *, recs_to_index: list) -> None:

        if self.__index_tei:
            for record_dict in recs_to_index:
                if "file" in record_dict:
                    try:
                        paper_hash = record_dict["id"]
                        tei_path = self.__get_tei_index_file(paper_hash=paper_hash)
                        tei_path.parents[0].mkdir(exist_ok=True, parents=True)
                        if Path(record_dict["file"]).is_file():
                            if not tei_path.is_file():
                                print(f"Create tei for {record_dict['file']}")
                            tei = colrev.env.tei_parser.TEIParser(
                                environment_manager=self.environment_manager,
                                pdf_path=Path(record_dict["file"]),
                                tei_path=tei_path,
                            )

                            record_dict["tei"] = str(tei_path)
                            record_dict["fulltext"] = tei.get_tei_str()

                            # self.__index_author(tei=tei, record_dict=record_dict)

                    except (
                        colrev_exceptions.TEIException,
                        AttributeError,
                    ):
                        pass

    # def __amend_record(self, *, paper_hash: str, record_dict: dict) -> None:
    #     # TODO

    #     # pylint: disable=too-many-locals

    #     saved_record_response = self.open_search.get(
    #         index=self.RECORD_INDEX,
    #         id=paper_hash,
    #     )
    #     saved_record_dict = saved_record_response["_source"]

    #     # Create fulltext backup to prevent bibtext parsing issues
    #     fulltext_backup = saved_record_dict.get("fulltext", "NA")
    #     if "fulltext" in saved_record_dict:
    #         del saved_record_dict["fulltext"]

    #     parsed_record_dict = self.__parse_record(record_dict=saved_record_dict)
    #     saved_record = colrev.record.Record(data=parsed_record_dict)
    #     record = colrev.record.Record(data=record_dict)

    #     # combine metadata_source_repository_paths in a semicolon-separated list
    #     metadata_source_repository_paths = record.data[
    #         "metadata_source_repository_paths"
    #     ]
    #     saved_record.data["metadata_source_repository_paths"] += (
    #         "\n" + metadata_source_repository_paths
    #     )

    #     record_dict = record.get_data()

    #     save_record_curated = "CURATED" in saved_record_dict.get(
    #         "colrev_masterdata_provenance"
    #     )

    #     # amend saved record
    #     for key, value in record_dict.items():
    #         # Note : the record from the first repository should take precedence)
    #         if key in saved_record.data or key in ["colrev_status"]:
    #             continue
    #         if save_record_curated and key in saved_record.data:
    #             continue

    #         field_provenance = colrev.record.Record(
    #             data=record_dict
    #         ).get_field_provenance(
    #             key=key,
    #             default_source=record.data.get(
    #                 "metadata_source_repository_paths", "None"
    #             ),
    #         )

    #         saved_record.update_field(
    #             key=key,
    #             value=value,
    #             source=field_provenance.get("source_info", "NA"),
    #         )

    #     saved_record_dict = saved_record.get_data(stringify=True)

    #     # Important: full-texts should be added after get_data (parsing records)
    #     # to avoid error-printouts by pybtex
    #     if "NA" != fulltext_backup:
    #         saved_record.data["fulltext"] = fulltext_backup
    #     elif "file" in record_dict:
    #         try:
    #             tei_path = self.__get_tei_index_file(paper_hash=paper_hash)
    #             tei_path.parents[0].mkdir(exist_ok=True, parents=True)
    #             if Path(record_dict["file"]).is_file():
    #                 tei = colrev.env.tei_parser.TEIParser(
    #                     environment_manager=self.environment_manager,
    #                     pdf_path=Path(record_dict["file"]),
    #                     tei_path=tei_path,
    #                 )
    #                 saved_record.data["fulltext"] = tei.get_tei_str()
    #         except (
    #             colrev_exceptions.TEIException,
    #             AttributeError,
    #             SerializationError,
    #             TransportError,
    #         ):
    #             pass

    #     # pylint: disable=unexpected-keyword-arg
    #     self.open_search.update(
    #         index=self.RECORD_INDEX,
    #         id=paper_hash,
    #         body={"doc": saved_record_dict},
    #         request_timeout=self.request_timeout,
    #     )

    def get_fields_to_remove(self, *, record_dict: dict) -> list:
        """Compares the record to available toc items and
        returns fields to remove (if any)"""
        # pylint: disable=too-many-return-statements

        fields_to_remove: typing.List[str] = []
        if "journal" not in record_dict and "article" != record_dict["ENTRYTYPE"]:
            return fields_to_remove

        internal_record_dict = deepcopy(record_dict)

        if all(x in internal_record_dict.keys() for x in ["volume", "number"]):

            try:
                toc_key_full = colrev.record.Record(
                    data=internal_record_dict
                ).get_toc_key()

                if self.__toc_exists(toc_item=toc_key_full):
                    return fields_to_remove
            except colrev_exceptions.NotTOCIdentifiableException:
                return fields_to_remove

            wo_nr = deepcopy(internal_record_dict)
            del wo_nr["number"]
            toc_key_wo_nr = colrev.record.Record(data=wo_nr).get_toc_key()
            if "NA" != toc_key_wo_nr:
                if self.__toc_exists(toc_item=toc_key_wo_nr):
                    fields_to_remove.append("number")
                    return fields_to_remove

            wo_vol = deepcopy(internal_record_dict)
            del wo_vol["volume"]
            toc_key_wo_vol = colrev.record.Record(data=wo_vol).get_toc_key()
            if "NA" != toc_key_wo_vol:
                if self.__toc_exists(toc_item=toc_key_wo_vol):
                    fields_to_remove.append("volume")
                    return fields_to_remove

            wo_vol_nr = deepcopy(internal_record_dict)
            del wo_vol_nr["volume"]
            del wo_vol_nr["number"]
            toc_key_wo_vol_nr = colrev.record.Record(data=wo_vol_nr).get_toc_key()
            if "NA" != toc_key_wo_vol_nr:
                if self.__toc_exists(toc_item=toc_key_wo_vol_nr):
                    fields_to_remove.append("number")
                    fields_to_remove.append("volume")
                    return fields_to_remove

        return fields_to_remove

    def __get_index_toc(self, *, record_dict: dict) -> typing.Tuple[str, str]:
        toc_key = colrev.record.Record(data=record_dict).get_toc_key()
        record_dict["colrev_id"] = colrev.record.Record(
            data=record_dict
        ).create_colrev_id()
        return toc_key, record_dict["colrev_id"]

    def __add_index_toc(self, *, toc_to_index: dict) -> None:
        list_to_add = list(toc_to_index.items())
        cur = self.__sqlite_connection.cursor()
        try:
            cur.executemany(f"INSERT INTO {self.TOC_INDEX} VALUES(?, ?)", list_to_add)
        except sqlite3.IntegrityError as exc:
            if self.verbose_mode:
                print(exc)
        finally:
            self.__sqlite_connection.commit()

    def __add_index_records(self, *, recs_to_index: list) -> None:

        list_to_add = [
            {k: v for k, v in el.items() if k in self.RECORDS_INDEX_KEYS}
            for el in recs_to_index
        ]

        collisions = []
        cur = self.__sqlite_connection.cursor()
        for item in list_to_add:
            for records_index_required_key in self.RECORDS_INDEX_KEYS:
                if records_index_required_key not in item:
                    item[records_index_required_key] = ""
            if "" == item["id"]:
                print("NO ID IN RECORD")
                continue
            try:
                cur.execute(
                    f"INSERT INTO {self.RECORD_INDEX} "
                    f"VALUES(:{', :'.join(self.RECORDS_INDEX_KEYS)})",
                    item,
                )
            except sqlite3.IntegrityError:
                # print(exc)
                collisions.append(item)

        self.__sqlite_connection.commit()

        # TODO : collisions (duplicate ids)
        # for collision in collisions:
        # ...
        # while True:
        #     # if not self.open_search.exists(index=self.RECORD_INDEX, id=hash):
        #     stored = self.__store_record(paper_hash=paper_hash, record_dict=record_dict)
        #     if stored:
        #         break
        #     # selected_row = self.__retrieve_by_id_from_sqlite(table_name="records", )
        #     saved_record_response = self.open_search.get(
        #         index=self.RECORD_INDEX,
        #         id=paper_hash,
        #     )
        #     saved_record = saved_record_response["_source"]
        #     saved_record_cid = colrev.record.Record(data=saved_record).create_colrev_id(
        #         assume_complete=True
        #     )
        #     if saved_record_cid == cid_to_index:
        #         # ok - no collision, update the record
        #         # Note : do not update (the record from the first repository
        #         # should take precedence - reset the index to update)
        #         self.__amend_record(paper_hash=paper_hash, record_dict=record_dict)
        #         break
        #     # to handle the collision:
        #     print(f"Collision: {paper_hash}")
        #     print(cid_to_index)
        #     print(saved_record_cid)
        #     print(saved_record)
        #     paper_hash = self.__increment_hash(paper_hash=paper_hash)

    def __get_record_from_row(self, *, row: dict) -> dict:
        parser = bibtex.Parser()
        bib_data = parser.parse_string(row["bibtex"])
        ret = colrev.dataset.Dataset.parse_records_dict(records_dict=bib_data.entries)
        retrieved_record = list(ret.values())[0]
        return retrieved_record

    def __retrieve_based_on_colrev_id(self, *, cids_to_retrieve: list) -> dict:
        # Note : may raise NotEnoughDataToIdentifyException

        for cid_to_retrieve in cids_to_retrieve:
            try:
                retrieved_record = self.__get_from_index_exact_match(
                    index_name=self.RECORD_INDEX,
                    key="colrev_id",
                    value=cid_to_retrieve,
                )
                return retrieved_record

            except colrev_exceptions.RecordNotInIndexException:
                continue  # continue with the next cid_to_retrieve

        raise colrev_exceptions.RecordNotInIndexException()

    def __retrieve_from_record_index(self, *, record_dict: dict) -> dict:
        # Note : may raise NotEnoughDataToIdentifyException

        record = colrev.record.Record(data=record_dict)
        if "colrev_id" in record.data:
            cid_to_retrieve = record.get_colrev_id()
        else:
            cid_to_retrieve = [record.create_colrev_id()]

        retrieved_record = self.__retrieve_based_on_colrev_id(
            cids_to_retrieve=cid_to_retrieve
        )
        if retrieved_record["ENTRYTYPE"] != record_dict["ENTRYTYPE"]:
            raise colrev_exceptions.RecordNotInIndexException
        return retrieved_record

    def __prepare_record_for_return(
        self,
        *,
        record_dict: dict,
        include_file: bool = False,
        include_colrev_ids: bool = False,
    ) -> dict:
        """Prepare a record for return (from local index)"""

        # pylint: disable=too-many-branches

        # Note : remove fulltext before parsing because it raises errors
        fulltext_backup = record_dict.get("fulltext", "NA")

        if "fulltext" in record_dict:
            del record_dict["fulltext"]

        keys_to_remove = (
            "colrev_origin",
            "fulltext",
            "tei_file",
            "grobid-version",
            "excl_criteria",
            "exclusion_criteria",
            "local_curated_metadata",
            "metadata_source_repository_paths",
        )

        for key in keys_to_remove:
            record_dict.pop(key, None)

        # Note: record['file'] should be an absolute path by definition
        # when stored in the LocalIndex
        if "file" in record_dict:
            if not Path(record_dict["file"]).is_file():
                del record_dict["file"]

        if not include_colrev_ids and "colrev_id" in record_dict:
            if "colrev_id" in record_dict:
                del record_dict["colrev_id"]

        if include_file:
            if "NA" != fulltext_backup:
                record_dict["fulltext"] = fulltext_backup
        else:
            if "file" in record_dict:
                del record_dict["file"]
            if "file" in record_dict.get("colrev_data_provenance", {}):
                del record_dict["colrev_data_provenance"]["file"]
            if "colrev_pdf_id" in record_dict:
                del record_dict["colrev_pdf_id"]
            if "colrev_pdf_id" in record_dict.get("colrev_data_provenance", {}):
                del record_dict["colrev_data_provenance"]["colrev_pdf_id"]

        record_dict["colrev_status"] = colrev.record.RecordState.md_prepared

        if "CURATED" in record_dict.get("colrev_masterdata_provenance", {}):
            identifier_string = (
                record_dict["colrev_masterdata_provenance"]["CURATED"]["source"]
                + "#"
                + record_dict["ID"]
            )
            record_dict["curation_ID"] = identifier_string

        return record_dict

    def search(self, *, query: dict) -> list[colrev.record.Record]:
        """Run a search for records"""

        self.__thread_lock.acquire(timeout=60)
        thread_connection = sqlite3.connect(self.SQLITE_PATH)
        thread_connection.row_factory = self.__dict_factory
        cur = thread_connection.cursor()
        selected_row = None
        records_to_return = []

        cur.execute(f"SELECT * FROM {self.RECORD_INDEX} WHERE {query}")
        for row in cur.fetchall():
            selected_row = row
            retrieved_record = self.__get_record_from_row(row=selected_row)

            retrieved_record = self.__prepare_record_for_return(
                record_dict=retrieved_record, include_file=False
            )
            records_to_return.append(colrev.record.Record(data=retrieved_record))

        self.__thread_lock.release()

        return records_to_return

    def __outlets_duplicated(self) -> bool:

        print("Validate curated metadata")

        try:

            curated_outlets = self.environment_manager.get_curated_outlets()

            if len(curated_outlets) != len(set(curated_outlets)):
                duplicated = [
                    item
                    for item, count in collections.Counter(curated_outlets).items()
                    if count > 1
                ]
                print(
                    f"Error: Duplicate outlets in curated_metadata : {','.join(duplicated)}"
                )
                return True

        except colrev_exceptions.CuratedOutletNotUnique as exc:
            print(exc)
            return True
        return False

    def _prepare_record_for_indexing(self, *, record_dict: dict) -> dict:

        # pylint: disable=too-many-branches
        if "colrev_status" not in record_dict:
            raise colrev_exceptions.RecordNotIndexableException()

        # It is important to exclude md_prepared if the LocalIndex
        # is used to dissociate duplicates
        if (
            record_dict["colrev_status"]
            in colrev.record.RecordState.get_non_processed_states()
        ):
            raise colrev_exceptions.RecordNotIndexableException()

        # Some prescreen_excluded records are not prepared
        if (
            record_dict["colrev_status"]
            == colrev.record.RecordState.rev_prescreen_excluded
        ):
            raise colrev_exceptions.RecordNotIndexableException()

        if "screening_criteria" in record_dict:
            del record_dict["screening_criteria"]
        # Note: if the colrev_pdf_id has not been checked,
        # we cannot use it for retrieval or preparation.
        post_pdf_prepared_states = colrev.record.RecordState.get_post_x_states(
            state=colrev.record.RecordState.pdf_prepared
        )
        if record_dict["colrev_status"] not in post_pdf_prepared_states:
            if "colrev_pdf_id" in record_dict:
                del record_dict["colrev_pdf_id"]

        # Note : this is the first run, no need to split/list
        if "colrev/curated_metadata" in record_dict["metadata_source_repository_paths"]:
            # Note : local_curated_metadata is important to identify non-duplicates
            # between curated_metadata_repositories
            record_dict["local_curated_metadata"] = "yes"

        # To fix pdf_hash fields that should have been renamed
        if "pdf_hash" in record_dict:
            record_dict["colrev_pdf_id"] = "cpid1:" + record_dict["pdf_hash"]
            del record_dict["pdf_hash"]

        if "colrev_origin" in record_dict:
            del record_dict["colrev_origin"]

        # Note : numbers of citations change regularly.
        # They should be retrieved from sources like crossref/doi.org
        if "cited_by" in record_dict:
            del record_dict["cited_by"]

        # Note : file paths should be absolute when added to the LocalIndex
        if "file" in record_dict:
            pdf_path = Path(record_dict["file"])
            if pdf_path.is_file():
                record_dict["file"] = str(pdf_path)
            else:
                del record_dict["file"]

        if record_dict.get("year", "NA").isdigit():
            record_dict["year"] = int(record_dict["year"])
        elif "year" in record_dict:
            del record_dict["year"]

        # Provenance should point to the original repository path.
        # If the provenance/source was example.bib (and the record is amended during indexing)
        # we wouldn't know where the example.bib belongs to.
        record = colrev.record.Record(data=record_dict)
        for key in list(record.data.keys()):
            if key not in colrev.record.Record.identifying_field_keys:
                if key not in colrev.record.Record.provenance_keys + [
                    "ID",
                    "ENTRYTYPE",
                    "local_curated_metadata",
                    "metadata_source_repository_paths",
                ]:
                    if key not in record.data.get("colrev_data_provenance", {}):
                        record.add_data_provenance(
                            key=key,
                            source=record_dict["metadata_source_repository_paths"],
                        )
                    else:
                        if (
                            "CURATED"
                            not in record.data["colrev_data_provenance"][key]["source"]
                        ):
                            record.add_data_provenance(
                                key=key,
                                source=record_dict["metadata_source_repository_paths"],
                            )
            else:
                if not record.masterdata_is_curated():
                    record.add_masterdata_provenance(
                        key=key, source=record_dict["metadata_source_repository_paths"]
                    )

        # Make sure that we don't add provenance information without corresponding fields
        if "colrev_data_provenance" in record.data:
            provenance_keys = list(record.data.get("colrev_data_provenance", {}).keys())
            for provenance_key in provenance_keys:
                if provenance_key not in record.data:
                    del record.data["colrev_data_provenance"][provenance_key]
        if not record.masterdata_is_curated():
            if "colrev_masterdata_provenance" in record.data:
                provenance_keys = list(
                    record.data.get("colrev_masterdata_provenance", {}).keys()
                )
                for provenance_key in provenance_keys:
                    if provenance_key not in record.data:
                        del record.data["colrev_masterdata_provenance"][provenance_key]

        return record.get_data()

    def __get_index_record(self, *, record_dict: dict) -> dict:

        try:
            record_dict = self._prepare_record_for_indexing(record_dict=record_dict)
            cid_to_index = colrev.record.Record(data=record_dict).create_colrev_id()
            record_dict["colrev_id"] = cid_to_index
            record_dict["citation_key"] = record_dict["ID"]
            record_dict["id"] = self.__get_record_hash(record_dict=record_dict)
        except colrev_exceptions.NotEnoughDataToIdentifyException as exc:
            missing_key = ""
            if exc.missing_fields is not None:
                missing_key = ",".join(exc.missing_fields)
            raise colrev_exceptions.RecordNotIndexableException(
                missing_key=missing_key
            ) from exc

        return record_dict

    def index_colrev_project(self, *, repo_source_path: Path) -> None:
        """Index a CoLRev project"""

        # pylint: disable=import-outside-toplevel
        # pylint: disable=redefined-outer-name
        # pylint: disable=cyclic-import
        # pylint: disable=too-many-branches
        # pylint: disable=too-many-locals
        import colrev.review_manager

        try:

            if not Path(repo_source_path).is_dir():
                print(f"Warning {repo_source_path} not a directory")
                return

            print(f"Index records from {repo_source_path}")
            os.chdir(repo_source_path)
            review_manager = colrev.review_manager.ReviewManager(
                path_str=str(repo_source_path)
            )

            check_operation = colrev.operation.CheckOperation(
                review_manager=review_manager
            )
            if not check_operation.review_manager.dataset.records_file.is_file():
                return
            records = check_operation.review_manager.dataset.load_records_dict()

            # Add metadata_source_repository_paths : list of repositories from which
            # the record was integrated. Important for is_duplicate(...)
            for record in records.values():
                record.update(metadata_source_repository_paths=repo_source_path)

            curation_endpoints = [
                x
                for x in check_operation.review_manager.settings.data.data_package_endpoints
                if x["endpoint"] == "colrev_built_in.colrev_curation"
            ]
            if curation_endpoints:
                curation_endpoint = curation_endpoints[0]
                # Set masterdata_provenace to CURATED:{url}
                curation_url = curation_endpoint["curation_url"]
                if check_operation.review_manager.settings.is_curated_masterdata_repo():
                    for record in records.values():
                        record.update(
                            colrev_masterdata_provenance=f"CURATED:{curation_url};;"
                        )

                # Add curation_url to curated fields (provenance)
                curated_fields = curation_endpoint["curated_fields"]
                for curated_field in curated_fields:

                    for record_dict in records.values():
                        colrev.record.Record(data=record_dict).add_data_provenance(
                            key=curated_field, source=f"CURATED:{curation_url}"
                        )

            # Set absolute file paths and set bibtex field (for simpler retrieval)
            for record in records.values():
                if "file" in record:
                    record.update(file=repo_source_path / Path(record["file"]))
                record["bibtex"] = review_manager.dataset.parse_bibtex_str(
                    recs_dict_in={record["ID"]: record}
                )

            recs_to_index = []
            toc_to_index: typing.Dict[str, str] = {}
            for record_dict in tqdm(records.values()):
                try:
                    copy_for_toc_index = deepcopy(record_dict)
                    record_dict = self.__get_index_record(record_dict=record_dict)
                    recs_to_index.append(record_dict)

                    if curation_endpoints and record_dict.get("ENTRYTYPE", "") in [
                        "article",
                        "inproceedings",
                    ]:
                        toc_item, colrev_id = self.__get_index_toc(
                            record_dict=copy_for_toc_index
                        )
                        if toc_item in toc_to_index:
                            toc_to_index[toc_item] += f";{colrev_id}"
                        else:
                            toc_to_index[toc_item] = colrev_id

                except (
                    colrev_exceptions.RecordNotIndexableException,
                    colrev_exceptions.NotTOCIdentifiableException,
                ) as exc:
                    if self.verbose_mode:
                        print(exc)
                        print(record_dict)

            # Select fields and insert into index (sqlite)
            self.__index_tei_document(recs_to_index=recs_to_index)
            self.__add_index_records(recs_to_index=recs_to_index)
            if curation_endpoints:
                self.__add_index_toc(toc_to_index=toc_to_index)

        except (colrev_exceptions.CoLRevException) as exc:
            print(exc)

    def index(self) -> None:
        """Index all registered CoLRev projects"""
        # import shutil

        # Note : this task takes long and does not need to run often
        session = requests_cache.CachedSession(
            str(colrev.env.environment_manager.EnvironmentManager.cache_path),
            backend="sqlite",
            expire_after=timedelta(days=30),
        )
        # Note : lambda is necessary to prevent immediate function call
        # pylint: disable=unnecessary-lambda
        Timer(0.1, lambda: session.remove_expired_responses()).start()

        if self.__outlets_duplicated():
            return

        print(f"Reset {self.RECORD_INDEX} and {self.TOC_INDEX}")
        # Note : the tei-directory should be removed manually.

        Path(self.SQLITE_PATH).unlink()
        self.__sqlite_connection = sqlite3.connect(self.SQLITE_PATH)
        cur = self.__sqlite_connection.cursor()
        cur.execute(f"drop table if exists {self.RECORD_INDEX}")
        cur.execute(
            f"CREATE TABLE {self.RECORD_INDEX}(id TEXT PRIMARY KEY, "
            + ",".join(self.RECORDS_INDEX_KEYS[1:])
            + ")"
        )
        cur.execute(f"drop table if exists {self.TOC_INDEX}")
        cur.execute(
            f"CREATE TABLE {self.TOC_INDEX}(toc_key TEXT PRIMARY KEY, colrev_ids)"
        )

        self.__sqlite_connection.commit()

        repo_source_paths = [
            x["repo_source_path"]
            for x in self.environment_manager.load_environment_registry()
        ]
        for repo_source_path in repo_source_paths:
            self.index_colrev_project(repo_source_path=repo_source_path)

        # for annotator in self.annotators_path.glob("*/annotate.py"):
        #     print(f"Load {annotator}")

        #     annotator_module = ....load_source("annotator_module", str(annotator))
        #     annotate = getattr(annotator_module, "annotate")
        #     annotate(self)
        # Note : es.update can use functions applied to each record (for the update)

    def get_year_from_toc(self, *, record_dict: dict) -> str:
        """Determine the year of a paper based on its table-of-content (journal-volume-number)"""
        print("get_year_from_toc currently not implemented")
        return "NOT_IMPLEMENTED"

        # TODO

        # try:
        #     toc_key = colrev.record.Record(data=record_dict).get_toc_key()
        #     toc_items = []
        #     if open_search_thread_instance.exists(index=self.TOC_INDEX, id=toc_key):
        #         res = self.__retrieve_toc_index(toc_key=toc_key)
        #         toc_items = res.get("colrev_ids", [])  # type: ignore

        #     if not toc_items:
        #         raise colrev_exceptions.TOCNotAvailableException()

        #     toc_records_colrev_id = toc_items[0]
        #     paper_hash = hashlib.sha256(
        #         toc_records_colrev_id.encode("utf-8")
        #     ).hexdigest()
        #     res = open_search_thread_instance.get(
        #         index=self.RECORD_INDEX,
        #         id=str(paper_hash),
        #     )
        #     record_dict = res["_source"]  # type: ignore
        #     year = record_dict.get("year", "NA")

        # except (
        #     colrev_exceptions.NotEnoughDataToIdentifyException,
        #     TransportError,
        #     SerializationError,
        #     colrev_exceptions.NotTOCIdentifiableException,
        # ) as exc:
        #     raise colrev_exceptions.TOCNotAvailableException() from exc

        # return year

    def __toc_exists(self, *, toc_item: str) -> bool:

        self.__thread_lock.acquire(timeout=60)
        thread_connection = sqlite3.connect(self.SQLITE_PATH)
        thread_connection.row_factory = self.__dict_factory
        cur = thread_connection.cursor()
        selected_row = None
        cur.execute(f"SELECT * FROM {self.TOC_INDEX} WHERE toc_key='{toc_item}'")
        for row in cur.fetchall():
            selected_row = row
            break
        self.__thread_lock.release()
        if not selected_row:
            return False
        return True

    def retrieve_from_toc(
        self,
        *,
        record_dict: dict,
        similarity_threshold: float,
        include_file: bool = False,
        search_across_tocs: bool = False,
    ) -> dict:
        """Retrieve a record from the toc (table-of-contents)"""
        # pylint: disable=too-many-locals
        # pylint: disable=too-many-branches

        try:
            toc_key = colrev.record.Record(data=record_dict).get_toc_key()
        except colrev_exceptions.NotTOCIdentifiableException as exc:
            # if not search_across_tocs:
            raise colrev_exceptions.RecordNotInIndexException() from exc

        # 1. get TOC
        toc_items = []
        if not self.__toc_exists(toc_item=toc_key):
            # TODO : search-across-tocs?
            raise colrev_exceptions.RecordNotInIndexException()

        # try:
        res = self.__get_from_index_exact_match(
            index_name=self.TOC_INDEX, key="toc_key", value=toc_key
        )
        toc_items = res.get("colrev_ids", [])  # type: ignore

        # TODO

        # print("retrieve_from_toc currently not implemented")
        # return {}

        # if search_across_tocs:
        #     try:
        #         toc_items: typing.List[str] = []
        #         partial_toc_key = colrev.record.Record(data=record_dict).get_toc_key()
        #         # pylint: disable=unexpected-keyword-arg
        #         resp = open_search_thread_instance.search(
        #             index=self.TOC_INDEX,
        #             body={
        #                 "query": {
        #                     "match_phrase": {
        #                         "toc_key": partial_toc_key.replace("|UNKNOWN", "") + "|"
        #                     }
        #                 }
        #             },
        #             size=2000,
        #         )

        #         retrieved_tocs = resp["hits"]["hits"]
        #         if "hits" not in resp["hits"]:
        #             raise colrev_exceptions.RecordNotInIndexException()

        #         toc_items = [
        #             z
        #             for x in retrieved_tocs
        #             for y, z in x["_source"].items()
        #             if y == "colrev_ids"
        #         ]
        #         toc_items = [item for sublist in toc_items for item in sublist]

        #     except (
        #         colrev_exceptions.NotTOCIdentifiableException,
        #         KeyError,
        #     ) as exc:
        #         raise colrev_exceptions.RecordNotInIndexException() from exc

        # if not toc_items:
        #     raise colrev_exceptions.RecordNotInIndexException()

        # 2. get most similar record_dict
        try:
            if search_across_tocs:
                record_colrev_id = colrev.record.Record(
                    data=record_dict
                ).create_colrev_id(assume_complete=True)

            else:
                record_colrev_id = colrev.record.Record(
                    data=record_dict
                ).create_colrev_id()
            sim_list = [0.0]

            for toc_records_colrev_id in toc_items:
                # Note : using a simpler similarity measure
                # because the publication outlet parameters are already identical
                sim_value = fuzz.ratio(record_colrev_id, toc_records_colrev_id) / 100
                sim_list.append(sim_value)

            if max(sim_list) > similarity_threshold:
                if search_across_tocs:
                    second_highest = list(set(sim_list))[-2]
                    # Require a minimum difference to the next most similar record
                    if (max(sim_list) - second_highest) < 0.2:
                        raise colrev_exceptions.RecordNotInIndexException()

                toc_records_colrev_id = toc_items[sim_list.index(max(sim_list))]

                record_dict = self.__get_from_index_exact_match(
                    index_name=self.RECORD_INDEX,
                    key="colrev_id",
                    value=toc_records_colrev_id,
                )

                return self.__prepare_record_for_return(
                    record_dict=record_dict, include_file=include_file
                )

            raise colrev_exceptions.RecordNotInTOCException(
                record_id=record_dict["ID"], toc_key=toc_key
            )

        except (
            colrev_exceptions.NotEnoughDataToIdentifyException,
            KeyError,
        ):
            pass

        raise colrev_exceptions.RecordNotInIndexException()

    def __get_from_index_exact_match(
        self, *, index_name: str, key: str, value: str
    ) -> dict:

        retrieved_record = {}

        self.__thread_lock.acquire(timeout=60)
        thread_connection = sqlite3.connect(self.SQLITE_PATH)
        thread_connection.row_factory = self.__dict_factory
        cur = thread_connection.cursor()

        # TODO : handle collisions
        # paper_hash = hashlib.sha256(cid_to_retrieve.encode("utf-8")).hexdigest()
        # Collision
        # paper_hash = self.__increment_hash(paper_hash=paper_hash)

        selected_row = None
        cur.execute(f"SELECT * FROM {index_name} WHERE {key}='{value}'")
        for row in cur.fetchall():
            selected_row = row
            break
        self.__thread_lock.release()

        if not selected_row:
            raise colrev_exceptions.RecordNotInIndexException()

        if self.RECORD_INDEX == index_name:
            retrieved_record = self.__get_record_from_row(row=selected_row)
        else:
            retrieved_record = selected_row

        if "colrev_id" == key:
            if value != colrev.record.Record(data=retrieved_record).create_colrev_id():
                raise colrev_exceptions.RecordNotInIndexException()
        else:
            if key not in retrieved_record:
                raise colrev_exceptions.RecordNotInIndexException()

            if value != retrieved_record[key]:
                raise colrev_exceptions.RecordNotInIndexException()

        return retrieved_record

    def retrieve_based_on_colrev_pdf_id(self, *, colrev_pdf_id: str) -> dict:
        """
        Convenience function to retrieve the indexed record_dict metadata
        based on a colrev_pdf_id
        """

        record_dict = self.__get_from_index_exact_match(
            index_name=self.RECORD_INDEX,
            key="colrev_pdf_id",
            value=colrev_pdf_id,
        )

        record_to_import = self.__prepare_record_for_return(
            record_dict=record_dict, include_file=True
        )
        if "file" in record_to_import:
            del record_to_import["file"]
        return record_to_import

    def retrieve(
        self,
        *,
        record_dict: dict,
        include_file: bool = False,
        include_colrev_ids: bool = False,
    ) -> dict:
        """
        Convenience function to retrieve the indexed record_dict metadata
        based on another record_dict
        """

        # To avoid modifications to the original record
        record_dict = deepcopy(record_dict)

        retrieved_record_dict: typing.Dict = {}
        # 1. Try the record index
        try:
            retrieved_record_dict = self.__retrieve_from_record_index(
                record_dict=record_dict
            )
        except (
            colrev_exceptions.RecordNotInIndexException,
            colrev_exceptions.NotEnoughDataToIdentifyException,
        ) as exc:
            if self.verbose_mode:
                print(exc)
                print(f"{record_dict['ID']} - no exact match")

        # 2. Try using global-ids
        if not retrieved_record_dict:
            remove_colrev_id = False
            if "colrev_id" not in record_dict:
                record_dict["colrev_id"] = colrev.record.Record(
                    data=record_dict
                ).create_colrev_id()
                remove_colrev_id = True
            for key, value in record_dict.items():
                if key not in self.global_keys or "ID" == key:
                    continue
                retrieved_record_dict = self.__get_from_index_exact_match(
                    index_name=self.RECORD_INDEX, key=key, value=value
                )
                if key in retrieved_record_dict:
                    if retrieved_record_dict[key] == value:
                        break
                retrieved_record_dict = {}
            if remove_colrev_id:
                del record_dict["colrev_id"]

        if not retrieved_record_dict:
            raise colrev_exceptions.RecordNotInIndexException(
                record_dict.get("ID", "no-key")
            )

        return self.__prepare_record_for_return(
            record_dict=retrieved_record_dict,
            include_file=include_file,
            include_colrev_ids=include_colrev_ids,
        )

    def is_duplicate(self, *, record1_colrev_id: list, record2_colrev_id: list) -> str:
        """Convenience function to check whether two records are a duplicate"""

        try:

            # Ensure that we receive actual lists
            # otherwise, __retrieve_based_on_colrev_id iterates over a string and
            # open_search_thread_instance.search returns random results
            assert isinstance(record1_colrev_id, list)
            assert isinstance(record2_colrev_id, list)

            # Prevent errors caused by short colrev_ids/empty lists
            if (
                any(len(cid) < 20 for cid in record1_colrev_id)
                or any(len(cid) < 20 for cid in record2_colrev_id)
                or 0 == len(record1_colrev_id)
                or 0 == len(record2_colrev_id)
            ):
                return "unknown"

            # Easy case: the initial colrev_ids overlap => duplicate
            initial_colrev_ids_overlap = not set(record1_colrev_id).isdisjoint(
                list(record2_colrev_id)
            )
            if initial_colrev_ids_overlap:
                return "yes"

            # Retrieve records from LocalIndex and use that information
            # to decide whether the records are duplicates

            r1_index = self.__retrieve_based_on_colrev_id(
                cids_to_retrieve=record1_colrev_id
            )
            r2_index = self.__retrieve_based_on_colrev_id(
                cids_to_retrieve=record2_colrev_id
            )
            # Each record may originate from multiple repositories simultaneously
            # see integration of records in __amend_record(...)
            # This information is stored in metadata_source_repository_paths (list)

            r1_metadata_source_repository_paths = r1_index[
                "metadata_source_repository_paths"
            ].split("\n")
            r2_metadata_source_repository_paths = r2_index[
                "metadata_source_repository_paths"
            ].split("\n")

            # There are no duplicates within repositories
            # because we only index records that are md_processed or beyond
            # see conditions of index_record(...)

            # The condition that two records are in the same repository is True if
            # their metadata_source_repository_paths overlap.
            # This does not change if records are also in non-overlapping repositories

            same_repository = not set(r1_metadata_source_repository_paths).isdisjoint(
                set(r2_metadata_source_repository_paths)
            )

            # colrev_ids must be used instead of IDs
            # because IDs of original repositories
            # are not available in the integrated record

            colrev_ids_overlap = not set(
                colrev.record.Record(data=r1_index).get_colrev_id()
            ).isdisjoint(
                list(list(colrev.record.Record(data=r2_index).get_colrev_id()))
            )

            if same_repository:
                if colrev_ids_overlap:
                    return "yes"
                return "no"

            # Curated metadata repositories do not curate outlets redundantly,
            # i.e., there are no duplicates between curated repositories.
            # see __outlets_duplicated(...)

            different_curated_repositories = (
                "CURATED" in r1_index.get("colrev_masterdata_provenance", "")
                and "CURATED" in r2_index.get("colrev_masterdata_provenance", "")
                and (
                    r1_index.get("colrev_masterdata_provenance", "a")
                    != r2_index.get("colrev_masterdata_provenance", "b")
                )
            )

            if different_curated_repositories:
                return "no"

        except (
            colrev_exceptions.RecordNotInIndexException,
            colrev_exceptions.NotEnoughDataToIdentifyException,
        ):
            pass

        return "unknown"


if __name__ == "__main__":
    pass
