#! /usr/bin/env python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import zope.interface
from dacite import from_dict
from PyPDF2 import PdfFileReader
from PyPDF2 import PdfFileWriter

import colrev.env.utils
import colrev.process
import colrev.record


if TYPE_CHECKING:
    import colrev.ops.prep_man

# pylint: disable=too-few-public-methods


@zope.interface.implementer(colrev.process.PrepManEndpoint)
class CoLRevCLIManPrep:
    """Manual preparation using the CLI (Not yet implemented)"""

    settings_class = colrev.process.DefaultSettings

    def __init__(
        self,
        *,
        prep_man_operation: colrev.ops.prep_man.PrepMan,  # pylint: disable=unused-argument
        settings: dict,
    ) -> None:
        self.settings = from_dict(data_class=self.settings_class, data=settings)

    def prepare_manual(
        self, prep_man_operation: colrev.ops.prep_man.PrepMan, records: dict
    ) -> dict:

        # saved_args = locals()

        md_prep_man_data = prep_man_operation.get_data()
        stat_len = md_prep_man_data["nr_tasks"]

        if 0 == stat_len:
            prep_man_operation.review_manager.logger.info(
                "No records to prepare manually"
            )

        print("Man-prep is not fully implemented (yet).\n")
        print(
            "Edit the records.bib directly, set the colrev_status to 'md_prepared' and "
            "create a commit.\n"  # call this script again to create a commit
        )

        # if prep_man_operation.review_manager.dataset.has_changes():
        #     if "y" == input("Create commit (y/n)?"):
        #         prep_man_operation.review_manager.create_commit(
        #            msg= "Manual preparation of records",
        #             manual_author=True,
        #             saved_args=saved_args,
        #         )
        #     else:
        #         input("Press Enter to exit.")
        # else:
        #     input("Press Enter to exit.")

        return records


@zope.interface.implementer(colrev.process.PrepManEndpoint)
class ExportManPrep:
    """Manual preparation based on exported and imported metadata (and PDFs if any)"""

    @dataclass
    class ExportManPrepSettings:
        name: str
        pdf_handling_mode: str = "symlink"

        _details = {
            "pdf_handling_mode": {
                "tooltip": "Indicates how linked PDFs are handled (symlink/copy_first_page)"
            },
        }

    settings_class = ExportManPrepSettings

    def __init__(
        self,
        *,
        prep_man_operation: colrev.ops.prep_man.PrepMan,  # pylint: disable=unused-argument
        settings: dict,
    ) -> None:

        assert settings["pdf_handling_mode"] in ["symlink", "copy_first_page"]

        self.settings = from_dict(data_class=self.settings_class, data=settings)

    def prepare_manual(
        self, prep_man_operation: colrev.ops.prep_man.PrepMan, records: dict
    ) -> dict:

        prep_man_path = prep_man_operation.review_manager.path / Path("prep_man")
        prep_man_path.mkdir(exist_ok=True)

        export_path = prep_man_path / Path("records_prep_man.bib")

        def copy_files_for_man_prep(records):

            prep_man_path_pdfs = prep_man_path / Path("pdfs")
            prep_man_path_pdfs.mkdir(exist_ok=True)
            # TODO : empty prep_man_path_pdfs

            for record in records.values():
                if "file" in record:
                    target_path = prep_man_path / Path(record["file"])
                    target_path.parents[0].mkdir(exist_ok=True, parents=True)

                    if "symlink" == self.settings.pdf_handling_mode:
                        target_path.symlink_to(Path(record["file"]).resolve())

                    if "copy_first_page" == self.settings.pdf_handling_mode:
                        pdf_reader = PdfFileReader(record["file"], strict=False)
                        if pdf_reader.getNumPages() >= 1:

                            writer = PdfFileWriter()
                            writer.addPage(pdf_reader.getPage(0))
                            with open(target_path, "wb") as outfile:
                                writer.write(outfile)

        def export_prep_man() -> None:
            prep_man_operation.review_manager.logger.info(
                f"Export records for man-prep to {export_path}"
            )

            man_prep_recs = {
                k: v
                for k, v in records.items()
                if colrev.record.RecordState.md_needs_manual_preparation
                == v["colrev_status"]
            }
            prep_man_operation.review_manager.dataset.save_records_dict_to_file(
                records=man_prep_recs, save_path=export_path
            )
            if any("file" in r for r in man_prep_recs.values()):
                copy_files_for_man_prep(records=man_prep_recs)

        def import_prep_man() -> None:
            prep_man_operation.review_manager.logger.info(
                f"Load import changes from {export_path}"
            )

            with open(export_path, encoding="utf8") as target_bib:
                man_prep_recs = (
                    prep_man_operation.review_manager.dataset.load_records_dict(
                        load_str=target_bib.read()
                    )
                )

            records = prep_man_operation.review_manager.dataset.load_records_dict()
            for record_id, record_dict in man_prep_recs.items():
                record = colrev.record.PrepRecord(data=record_dict)
                record.update_masterdata_provenance(
                    unprepared_record=record.copy(),
                    review_manager=prep_man_operation.review_manager,
                )
                record.set_status(target_state=colrev.record.RecordState.md_prepared)
                for k in list(record.data.keys()):
                    if k in ["colrev_status"]:
                        continue
                    if k in records[record_id]:
                        if record.data[k] != records[record_id][k]:
                            if k in record.data.get("colrev_masterdata_provenance", {}):
                                record.add_masterdata_provenance(
                                    key=k, source="man_prep"
                                )
                            else:
                                record.add_data_provenance(key=k, source="man_prep")
                    else:
                        if k in records[record_id]:
                            del records[record_id][k]
                        if k in record.data.get("colrev_masterdata_provenance", {}):
                            record.add_masterdata_provenance(
                                key=k, source="man_prep", note="not_missing"
                            )
                        else:
                            record.add_data_provenance(
                                key=k, source="man_prep", note="not_missing"
                            )
                records[record_id] = record.get_data()

            prep_man_operation.review_manager.dataset.save_records_dict(records=records)
            prep_man_operation.review_manager.dataset.add_record_changes()
            prep_man_operation.review_manager.create_commit(
                msg="Prep-man (ExportManPrep)"
            )

            prep_man_operation.review_manager.dataset.set_ids()
            prep_man_operation.review_manager.create_commit(
                msg="Set IDs", script_call="colrev prep", saved_args={}
            )

        if not export_path.is_file():
            export_prep_man()
        else:
            if "y" == input(f"Import changes from {export_path} [y,n]?"):
                import_prep_man()

        return records


@zope.interface.implementer(colrev.process.PrepManEndpoint)
class CurationJupyterNotebookManPrep:
    """Manual preparation based on a Jupyter Notebook"""

    settings_class = colrev.process.DefaultSettings

    def __init__(
        self, *, prep_man_operation: colrev.ops.prep_man.PrepMan, settings: dict
    ) -> None:
        self.settings = from_dict(data_class=self.settings_class, data=settings)

        Path("prep_man").mkdir(exist_ok=True)
        if not Path("prep_man/prep_man_curation.ipynb").is_file():
            prep_man_operation.review_manager.logger.info(
                f"Activated jupyter notebook to"
                f"{Path('prep_man/prep_man_curation.ipynb')}"
            )
            colrev.env.utils.retrieve_package_file(
                template_file=Path("template/prep_man_curation.ipynb"),
                target=Path("prep_man/prep_man_curation.ipynb"),
            )

    def prepare_manual(
        self,
        prep_man_operation: colrev.ops.prep_man.PrepMan,  # pylint: disable=unused-argument
        records: dict,
    ) -> dict:

        input(
            "Navigate to the jupyter notebook available at\n"
            "prep_man/prep_man_curation.ipynb\n"
            "Press Enter to continue."
        )
        return records


if __name__ == "__main__":
    pass