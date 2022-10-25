#! /usr/bin/env python
"""Consolidation of metadata based on DOI metadata as a prep operation"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import timeout_decorator
import zope.interface
from dacite import from_dict
from dataclasses_jsonschema import JsonSchemaMixin

import colrev.env.package_manager
import colrev.ops.built_in.database_connectors
import colrev.ops.search_sources
import colrev.record

if TYPE_CHECKING:
    import colrev.ops.prep

# pylint: disable=too-few-public-methods
# pylint: disable=duplicate-code


@zope.interface.implementer(colrev.env.package_manager.PrepPackageEndpointInterface)
@dataclass
class DOIMetadataPrep(JsonSchemaMixin):
    """Prepares records based on doi.org metadata"""

    settings_class = colrev.env.package_manager.DefaultSettings

    source_correction_hint = (
        "ask the publisher to correct the metadata"
        + " (see https://www.crossref.org/blog/"
        + "metadata-corrections-updates-and-additions-in-metadata-manager/"
    )
    always_apply_changes = False

    def __init__(
        self,
        *,
        prep_operation: colrev.ops.prep.Prep,  # pylint: disable=unused-argument
        settings: dict,
    ) -> None:
        self.settings = from_dict(data_class=self.settings_class, data=settings)

    @timeout_decorator.timeout(60, use_signals=False)
    def prepare(
        self, prep_operation: colrev.ops.prep.Prep, record: colrev.record.PrepRecord
    ) -> colrev.record.Record:
        """Prepare the record by retrieving its metadata from doi.org"""

        if "doi" not in record.data:
            return record
        colrev.ops.built_in.database_connectors.DOIConnector.retrieve_doi_metadata(
            review_manager=prep_operation.review_manager,
            record=record,
            timeout=prep_operation.timeout,
        )
        colrev.ops.built_in.database_connectors.DOIConnector.get_link_from_doi(
            record=record,
            review_manager=prep_operation.review_manager,
        )
        return record


if __name__ == "__main__":
    pass