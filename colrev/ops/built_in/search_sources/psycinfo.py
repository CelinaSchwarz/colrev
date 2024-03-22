#! /usr/bin/env python
"""SearchSource: PsycINFO"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import zope.interface
from dacite import from_dict
from dataclasses_jsonschema import JsonSchemaMixin

import colrev.env.package_manager
import colrev.record
from colrev.constants import ENTRYTYPES
from colrev.constants import Fields
from colrev.constants import SearchType

# pylint: disable=unused-argument
# pylint: disable=duplicate-code


@zope.interface.implementer(
    colrev.env.package_manager.SearchSourcePackageEndpointInterface
)
@dataclass
class PsycINFOSearchSource(JsonSchemaMixin):
    """PsycINFO"""

    settings_class = colrev.env.package_manager.DefaultSourceSettings
    endpoint = "colrev.psycinfo"
    # pylint: disable=colrev-missed-constant-usage
    source_identifier = "url"
    search_types = [SearchType.DB]

    ci_supported: bool = False
    heuristic_status = colrev.env.package_manager.SearchSourceHeuristicStatus.oni
    short_name = "PsycInfo (APA)"
    docs_link = (
        "https://github.com/CoLRev-Environment/colrev/blob/main/"
        + "colrev/ops/built_in/search_sources/psycinfo.md"
    )
    db_url = "https://www.apa.org/search"

    def __init__(
        self, *, source_operation: colrev.operation.Operation, settings: dict
    ) -> None:
        self.search_source = from_dict(data_class=self.settings_class, data=settings)
        self.source_operation = source_operation
        self.review_manager = source_operation.review_manager

    @classmethod
    def heuristic(cls, filename: Path, data: str) -> dict:
        """Source heuristic for PsycINFO"""

        result = {"confidence": 0.1}

        # Note : no features in bib file for identification

        if data.startswith(
            "Provider: American Psychological Association\nDatabase: PsycINFO"
        ):
            result["confidence"] = 1.0

        return result

    @classmethod
    def add_endpoint(
        cls,
        operation: colrev.ops.search.Search,
        params: dict,
    ) -> colrev.settings.SearchSource:
        """Add SearchSource as an endpoint (based on query provided to colrev search -a )"""

        return operation.add_db_source(
            search_source_cls=cls,
            params=params,
        )

    def search(self, rerun: bool) -> None:
        """Run a search of Psycinfo"""

        if self.search_source.search_type == SearchType.DB:
            self.source_operation.run_db_search(  # type: ignore
                search_source_cls=self.__class__,
                source=self.search_source,
            )
            return

        raise NotImplementedError

    def prep_link_md(
        self,
        prep_operation: colrev.ops.prep.Prep,
        record: colrev.record.Record,
        save_feed: bool = True,
        timeout: int = 10,
    ) -> colrev.record.Record:
        """Not implemented"""
        return record

    def _load_ris(self) -> dict:
        def entrytype_setter(record_dict: dict) -> None:
            if record_dict["TY"] == "JOUR":
                record_dict[Fields.ENTRYTYPE] = ENTRYTYPES.ARTICLE
            elif record_dict["TY"] == "RPRT":
                record_dict[Fields.ENTRYTYPE] = ENTRYTYPES.TECHREPORT
            elif record_dict["TY"] == "CHAP":
                record_dict[Fields.ENTRYTYPE] = ENTRYTYPES.INBOOK
            else:
                record_dict[Fields.ENTRYTYPE] = ENTRYTYPES.MISC

        def field_mapper(record_dict: dict) -> None:

            key_maps = {
                ENTRYTYPES.ARTICLE: {
                    "Y1": Fields.YEAR,
                    "A1": Fields.AUTHOR,
                    "T1": Fields.TITLE,
                    "JF": Fields.JOURNAL,
                    "N2": Fields.ABSTRACT,
                    "VL": Fields.VOLUME,
                    "IS": Fields.NUMBER,
                    "KW": Fields.KEYWORDS,
                    "DO": Fields.DOI,
                    "PB": Fields.PUBLISHER,
                    "PMID": Fields.PUBMED_ID,
                    "SN": Fields.ISSN,
                },
            }

            key_map = key_maps[record_dict[Fields.ENTRYTYPE]]
            for ris_key in list(record_dict.keys()):
                if ris_key in key_map:
                    standard_key = key_map[ris_key]
                    record_dict[standard_key] = record_dict.pop(ris_key)

            if "SP" in record_dict and "EP" in record_dict:
                record_dict[Fields.PAGES] = (
                    f"{record_dict.pop('SP')}--{record_dict.pop('EP')}"
                )

            if Fields.AUTHOR in record_dict and isinstance(
                record_dict[Fields.AUTHOR], list
            ):
                record_dict[Fields.AUTHOR] = " and ".join(record_dict[Fields.AUTHOR])
            if Fields.EDITOR in record_dict and isinstance(
                record_dict[Fields.EDITOR], list
            ):
                record_dict[Fields.EDITOR] = " and ".join(record_dict[Fields.EDITOR])
            if Fields.KEYWORDS in record_dict and isinstance(
                record_dict[Fields.KEYWORDS], list
            ):
                record_dict[Fields.KEYWORDS] = ", ".join(record_dict[Fields.KEYWORDS])

            record_dict.pop("TY", None)
            record_dict.pop("Y2", None)
            record_dict.pop("DB", None)
            record_dict.pop("C1", None)
            record_dict.pop("T3", None)
            record_dict.pop("AD", None)
            record_dict.pop("CY", None)
            record_dict.pop("M3", None)
            record_dict.pop("EP", None)
            record_dict.pop("ER", None)

            for key, value in record_dict.items():
                record_dict[key] = str(value)

        records = colrev.loader.load_utils.load(
            filename=self.search_source.filename,
            unique_id_field="ID",
            entrytype_setter=entrytype_setter,
            field_mapper=field_mapper,
            logger=self.review_manager.logger,
        )

        return records

    def load(self, load_operation: colrev.ops.load.Load) -> dict:
        """Load the records from the SearchSource file"""

        if self.search_source.filename.suffix == ".ris":
            return self._load_ris()

        raise NotImplementedError

    def prepare(
        self, record: colrev.record.Record, source: colrev.settings.SearchSource
    ) -> colrev.record.Record:
        """Source-specific preparation for PsycINFO"""

        return record
