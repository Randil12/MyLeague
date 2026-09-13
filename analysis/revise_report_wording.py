"""Élimine les dernières formulations figées du dossier consolidé."""

from __future__ import annotations

import json

from docx import Document

import analysis.build_consolidated_report as build
import analysis.update_competency_evidence as base


def main() -> None:
    current = json.loads(base.RESULTS.read_text(encoding="utf-8"))
    n_changed = current["hypothesis_2"]["n_changed"]
    doc = Document(build.OUTPUT)
    table = base.find_table(doc, "Question")
    base.replace_cell_text(
        table.rows[2].cells[3],
        f"Poursuivre la collecte ; {n_changed} champions modifiés donnent encore "
        "une puissance limitée.",
    )
    doc.save(build.OUTPUT)
    print(build.OUTPUT)


if __name__ == "__main__":
    main()
