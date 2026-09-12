"""Génère le livrable Word final et synchronise ses tableaux."""

from __future__ import annotations

import json

from docx import Document
from docx.enum.style import WD_STYLE_TYPE

import analysis.build_consolidated_report as build
import analysis.update_competency_evidence as base


def open_with_required_styles(*args, **kwargs):
    doc = Document(*args, **kwargs)
    names = {style.name for style in doc.styles}
    if "Table Grid" not in names:
        doc.styles.add_style("Table Grid", WD_STYLE_TYPE.TABLE)
    if "List Bullet" not in names:
        doc.styles.add_style("List Bullet", WD_STYLE_TYPE.PARAGRAPH)
    return doc


def main() -> None:
    build.Document = open_with_required_styles
    build.main()

    current = json.loads(base.RESULTS.read_text(encoding="utf-8"))
    doc = Document(build.OUTPUT)
    table = base.find_table(doc, "Patch")
    patches = current["patches"]
    while len(table.rows) < len(patches) + 1:
        table.add_row()
    for row, item in zip(table.rows[1:], patches, strict=True):
        build.fill_row(
            row,
            [item["patch"], item["total_matches"], f"{item['avg_duration_min']:.1f} min"],
        )
    doc.save(build.OUTPUT)
    print(build.OUTPUT)


if __name__ == "__main__":
    main()
