"""Point d'entrée robuste pour générer le dossier Bloc 2 consolidé."""

from __future__ import annotations

import json

from docx import Document as open_document
from docx.enum.style import WD_STYLE_TYPE

import analysis.build_consolidated_report as build
import analysis.update_competency_evidence as base


def document_with_table_grid(*args, **kwargs):
    doc = open_document(*args, **kwargs)
    table_style_names = {
        style.name for style in doc.styles if style.type == WD_STYLE_TYPE.TABLE
    }
    if "Table Grid" not in table_style_names:
        doc.styles.add_style("Table Grid", WD_STYLE_TYPE.TABLE)
    return doc


def main() -> None:
    build.Document = document_with_table_grid
    build.main()

    current = json.loads(base.RESULTS.read_text(encoding="utf-8"))
    doc = open_document(build.OUTPUT)
    table = base.find_table(doc, "Patch")
    patches = current["patches"]
    while len(table.rows) < len(patches) + 1:
        table.add_row()
    for row, item in zip(table.rows[1:], patches, strict=True):
        build.fill_row(
            row,
            [
                item["patch"],
                item["total_matches"],
                f"{item['avg_duration_min']:.1f} min",
            ],
        )
    doc.save(build.OUTPUT)
    print(build.OUTPUT)


if __name__ == "__main__":
    main()
