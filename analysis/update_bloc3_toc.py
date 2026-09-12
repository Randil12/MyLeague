"""Injecte dans le sommaire les pages calculées sur le PDF de contrôle."""

from pathlib import Path

from docx import Document
from pypdf import PdfReader

import finalize_bloc3_submission as finalizer


ROOT = Path(__file__).resolve().parents[1]
DOCX = ROOT / "docs" / "Bloc3_David_Nguyen_M2_final.docx"
PDF = ROOT / ".cache" / "bloc3_render" / "Bloc3_David_Nguyen_M2_final.pdf"


def main() -> None:
    reader = PdfReader(PDF)
    page_texts = [page.extract_text() or "" for page in reader.pages]

    keys = [
        "Introduction",
        "A3.1 Cadrage, dimensionnement et documentation",
        "3.1.1 Cadrage du projet",
        "3.1.2 Dimensionnement du projet",
        "3.1.3 Documentation projet",
        "A3.2 Planification et suivi du projet",
        "3.2.1 Planification du projet",
        "3.2.2 Suivi de l'avancement",
        "A3.3 Compétences, équipe et arbitrages",
        "3.3.1 Plan de développement des compétences",
        "3.3.2 Pilotage de l'équipe et communication",
        "3.3.3 Arbitrages et réajustements",
        "A3.4 Veille et pratiques responsables",
        "3.4.1 Méthodologie de veille technologique et réglementaire",
        "3.4.2 Plan d'actions RSE, sécurité, éthique et confidentialité",
        "Conclusion",
        "Annexes",
    ]
    keys.extend(f"Annexe {number}" for number in range(1, 16))

    page_map: dict[str, int] = {}
    for key in keys:
        needle = f"{key} :" if key.startswith("Annexe ") else key
        matches = [
            page_number
            for page_number, text in enumerate(page_texts, start=1)
            if page_number >= 3 and needle in text
        ]
        if not matches:
            raise RuntimeError(f"Titre absent du rendu PDF: {key}")
        page_map[key] = matches[0]

    doc = Document(DOCX)
    finalizer.replace_toc(doc, page_map)
    doc.save(DOCX)
    for key, page in page_map.items():
        print(f"{key}: {page}")


if __name__ == "__main__":
    main()
