"""Finalise le dossier consolidé et synchronise le tableau d'échantillon."""

from __future__ import annotations

import json

from docx import Document

import analysis.build_consolidated_report as build
import analysis.update_competency_evidence as base


def main() -> None:
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
