"""Produit la version finale et paginable du dossier Bloc 3.

Le script part toujours du DOCX remis par l'utilisateur. Il harmonise les
preuves avec le Bloc 2, déplace la piste d'audit en annexe et applique les
contraintes de forme demandées.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_BREAK, WD_LINE_SPACING, WD_PARAGRAPH_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "Bloc3_David_Nguyen_M2.docx"
OUTPUT = ROOT / "docs" / "Bloc3_David_Nguyen_M2_final.docx"


def replace_paragraph(paragraph, text: str) -> None:
    if paragraph.runs:
        paragraph.runs[0].text = text
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(text)


def paragraph_starting(doc: Document, prefix: str):
    matches = [p for p in doc.paragraphs if p.text.startswith(prefix)]
    if len(matches) != 1:
        raise RuntimeError(f"Paragraphe attendu une fois, trouvé {len(matches)} fois: {prefix}")
    return matches[0]


def heading_starting(doc: Document, prefix: str):
    matches = [
        p
        for p in doc.paragraphs
        if p.text.startswith(prefix) and p.style and p.style.name.startswith("Heading")
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Titre attendu une fois, trouvé {len(matches)} fois: {prefix}")
    return matches[0]


def replace_starting(doc: Document, prefix: str, text: str) -> None:
    replace_paragraph(paragraph_starting(doc, prefix), text)


def set_cell(cell, text: str) -> None:
    replace_paragraph(cell.paragraphs[0], text)
    for paragraph in cell.paragraphs[1:]:
        replace_paragraph(paragraph, "")


def set_repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    if tr_pr.find(qn("w:tblHeader")) is None:
        tr_pr.append(OxmlElement("w:tblHeader"))


def prevent_row_split(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    if tr_pr.find(qn("w:cantSplit")) is None:
        tr_pr.append(OxmlElement("w:cantSplit"))


def set_page_break_before(paragraph, enabled: bool = True) -> None:
    paragraph.paragraph_format.page_break_before = enabled


def move_after(element, destination) -> None:
    destination.addnext(element)


def remove_existing_toc_field(doc: Document) -> None:
    """Supprime l'ancien champ TOC et ses résultats figés, dont Remerciements."""
    body = doc._element.body
    children = list(body)
    start = None
    end = None
    for index, child in enumerate(children):
        instructions = [node.text or "" for node in child.iter(qn("w:instrText"))]
        if start is None and any("TOC" in instruction for instruction in instructions):
            start = index
        if start is not None:
            field_ends = [
                node
                for node in child.iter(qn("w:fldChar"))
                if node.get(qn("w:fldCharType")) == "end"
            ]
            if field_ends:
                end = index
                break
    if start is None or end is None:
        raise RuntimeError("Ancien champ de sommaire introuvable")
    for child in children[start : end + 1]:
        body.remove(child)


def style_document(doc: Document) -> None:
    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()
        if paragraph.style and paragraph.style.name == "normal" and text:
            paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
            paragraph.paragraph_format.first_line_indent = Cm(0.7)
            paragraph.paragraph_format.space_after = Pt(3)

    for table in doc.tables:
        if table.rows:
            set_repeat_table_header(table.rows[0])
        for row in table.rows:
            prevent_row_split(row)
            for cell in row.cells:
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.first_line_indent = Cm(0)
                    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
                    paragraph.paragraph_format.space_after = Pt(1)
                    for run in paragraph.runs:
                        run.font.size = Pt(8.5)

    for paragraph in doc.paragraphs:
        if paragraph.style and paragraph.style.name.startswith("Heading"):
            paragraph.paragraph_format.keep_with_next = True


def sanitize_visible_text(doc: Document) -> None:
    def clean(text: str) -> str:
        text = text.replace("--", "-")
        text = text.replace(" ; ", ". ")
        text = text.replace("; ", ". ")
        return text.replace(";", ",")

    for paragraph in doc.paragraphs:
        if ";" in paragraph.text or "--" in paragraph.text:
            replace_paragraph(paragraph, clean(paragraph.text))
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if ";" in cell.text or "--" in cell.text:
                    set_cell(cell, clean(cell.text))


def replace_toc(doc: Document, page_map: dict[str, int] | None) -> None:
    entries = [
        ("Introduction", "Introduction"),
        ("A3.1 Cadrage, dimensionnement et documentation", "A3.1 Cadrage, dimensionnement et documentation"),
        ("3.1.1 Cadrage du projet", "3.1.1 Cadrage du projet"),
        ("3.1.2 Dimensionnement du projet", "3.1.2 Dimensionnement du projet"),
        ("3.1.3 Documentation projet", "3.1.3 Documentation projet"),
        ("A3.2 Planification et suivi du projet", "A3.2 Planification et suivi du projet"),
        ("3.2.1 Planification du projet", "3.2.1 Planification du projet"),
        ("3.2.2 Suivi de l'avancement", "3.2.2 Suivi de l'avancement"),
        ("A3.3 Compétences, équipe et arbitrages", "A3.3 Compétences, équipe et arbitrages"),
        ("3.3.1 Plan de développement des compétences", "3.3.1 Plan de développement des compétences"),
        ("3.3.2 Pilotage de l'équipe et communication", "3.3.2 Pilotage de l'équipe et communication"),
        ("3.3.3 Arbitrages et réajustements", "3.3.3 Arbitrages et réajustements"),
        ("A3.4 Veille et pratiques responsables", "A3.4 Veille et pratiques responsables"),
        ("3.4.1 Méthodologie de veille technologique et réglementaire", "3.4.1 Méthodologie de veille technologique et réglementaire"),
        ("3.4.2 Plan d'actions RSE, sécurité, éthique et confidentialité", "3.4.2 Plan d'actions RSE, sécurité, éthique et confidentialité"),
        ("Conclusion", "Conclusion"),
        ("Annexes", "Annexes"),
    ]
    entries.extend((f"Annexe {number}", f"Annexe {number}") for number in range(1, 16))

    toc_start = next(i for i, p in enumerate(doc.paragraphs) if p.text == "Sommaire")
    intro_index = next(i for i, p in enumerate(doc.paragraphs) if p.text == "Introduction")
    toc_paragraphs = doc.paragraphs[toc_start + 1 : intro_index]
    if len(toc_paragraphs) != len(entries):
        raise RuntimeError(f"Sommaire inattendu: {len(toc_paragraphs)} lignes pour {len(entries)} entrées")

    for paragraph, (label, key) in zip(toc_paragraphs, entries, strict=True):
        page = "À actualiser" if page_map is None else str(page_map[key])
        replace_paragraph(paragraph, f"{label}\t{page}")
        paragraph.paragraph_format.first_line_indent = Cm(0)
        paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.keep_with_next = False
        for run in paragraph.runs:
            run.font.size = Pt(8.5)


def apply_content_corrections(doc: Document) -> None:
    replace_starting(
        doc,
        "Les termes suivis d'un astérisque",
        "Référence commune avec le Bloc 2. Les résultats proviennent du snapshot Gold "
        "horodaté le 28 juillet 2026 à 00 h 01 UTC. Sur le patch 16.14, Spearman porte "
        "sur 137 champions, donne ρ = 0,451 et p = 3,00 × 10⁻⁸, donc H0 est rejetée. "
        "Mann-Whitney compare 6 champions modifiés à 122 témoins, donne U = 276 et "
        "p = 0,313, donc H0 n'est pas rejetée. Le build de référence comprend 18 modèles "
        "et 63 tests de données, soit 81 opérations réussies. Le protocole de lecture en "
        "moins de deux minutes et la formation de 45 minutes sont prêts, mais n'ont pas "
        "encore été exécutés auprès du staff Nexus. Les termes suivis d'un astérisque sont "
        "définis dans le glossaire en annexe.",
    )

    replace_starting(
        doc,
        "L'estimation par phase retenue au cadrage",
        "L'estimation retenue au cadrage totalise 5 jours de mise en place, 12 jours "
        "d'ingestion et d'orchestration, 10 jours de modélisation dbt, 8 jours d'analyses "
        "statistiques, 8 jours de restitution, 6 jours de documentation et 3 jours de "
        "pilotage. Le libellé de référence est 52 jours pour la phase intensive et 70 jours "
        "pour le projet complet, après ajout des 18 jours équivalents de l'amont. Le détail "
        "figure en annexe 11.",
    )
    replace_starting(
        doc,
        "Le chiffrage distingue deux périodes",
        "Le chiffrage distingue 18 jours-homme équivalents de janvier à juin et 52 jours-homme "
        "pour la phase intensive du 22 juin à la fin août. Le libellé de référence est donc "
        "52 jours pour la phase intensive et 70 jours pour le projet complet. Au TJM de "
        "400 euros, la valorisation atteint 28 000 euros, dont 20 800 euros pour la phase "
        "intensive. Il s'agit d'une valorisation sans facturation réelle. Le coût monétaire "
        "direct reste proche de zéro grâce aux outils gratuits utilisés dans le cadre du projet.",
    )

    replace_starting(
        doc,
        "Le tableau de bord ci-dessous consolide",
        "Le tableau de bord ci-dessous consolide l'état du projet à la revue du 16 août 2026. "
        "À la fin de S8, la phase intensive compte 43 jours consommés pour 42 jours prévus, "
        "soit 83 pour cent de son budget de 52 jours. Sept jalons sur huit sont atteints. "
        "La piste d'audit hebdomadaire complète est déplacée en annexe 12.",
    )
    replace_starting(
        doc,
        "L'écart de deux jours sur le build dbt",
        "L'arbitrage de nomenclature est ouvert en S5 après la revue du 22 juillet, puis la "
        "normalisation est implémentée le 26 juillet. Le build et le snapshot du 28 juillet, "
        "en S6, valident le recouvrement entre les sources. Le report de l'export CSV absorbe "
        "l'écart sans déplacer la remise finale.",
    )
    replace_starting(
        doc,
        "La piste d'audit chiffrée ci-dessous",
        "La piste d'audit en annexe 12 réconcilie les 18 jours équivalents de l'amont, les "
        "52 jours de la phase intensive et les 70 jours du projet complet. Le cumul y intègre "
        "l'amont tandis que l'écart porte uniquement sur la phase intensive.",
    )
    replace_starting(
        doc,
        "Lecture : l'écart se creuse",
        "Lecture de la chronologie. L'écart atteint trois jours en S4 en raison des reprises "
        "d'ingestion. L'arbitrage est engagé le 22 juillet en S5 et la correction est livrée "
        "le 26 juillet. Sa validation intervient le 28 juillet en S6 avec le build complet et "
        "le snapshot statistique. L'avance prise ensuite sur les analyses ramène l'écart à deux "
        "jours, puis le report de l'export CSV le neutralise dans la projection finale.",
    )

    replace_starting(
        doc,
        "Le projet réel étant individuel",
        "Le projet réel étant individuel, le pilotage repose sur des interactions documentées "
        "avec le tuteur pédagogique et sur des relectures ponctuelles par des pairs. Ces échanges "
        "couvrent le cadrage de mars, l'architecture du 21 juin, la revue de fin juillet et la "
        "relecture des dossiers en août. Ils prouvent une coordination réelle autour du projet. "
        "Ils ne sont pas présentés comme l'exécution du test utilisateur en moins de deux minutes, "
        "qui reste à conduire avec un membre du staff Nexus.",
    )
    replace_starting(
        doc,
        "Le scénario Nexus Esport Academy projette une équipe de trois personnes",
        "Le scénario Nexus Esport Academy projette une équipe de trois personnes. Sur les 52 jours "
        "de la phase intensive, le calcul par activité attribue 21 jours au data engineer, 18 jours "
        "à l'analyste et 13 jours au coach référent. La matrice RACI répartit les responsabilités, "
        "tandis que l'annexe 14 présente les charges phase par phase et vérifie que chaque ligne et "
        "chaque total se réconcilient. Ce scénario démontre la méthode prévue. Il ne constitue pas "
        "la preuve d'un pilotage d'équipe déjà exercé.",
    )
    replace_starting(
        doc,
        "Trois outils structurent la collaboration projetée",
        "Trois outils structurent la collaboration projetée. Trello rend les tâches et la charge "
        "visibles. GitHub porte la collaboration technique. Discord assure les échanges quotidiens, "
        "avec transcription de chaque décision dans Trello. Dans le projet réel, le workflow CI "
        "versionné le 26 juillet déclenche ruff, pytest, dbt parse et la validation de la configuration "
        "Docker Compose à chaque push et demande de fusion. La revue croisée avant fusion relève du "
        "scénario d'équipe.",
    )

    replace_starting(
        doc,
        "Un résultat concret illustre le dispositif",
        "Un résultat concret illustre le dispositif. La revue du 22 juillet 2026 a identifié "
        "la nomenclature annuelle 26.x de Leaguepedia face au format 16.x de Riot. Une carte "
        "Trello a ouvert l'arbitrage en S5. La normalisation a été livrée le 26 juillet, puis "
        "validée en S6 par le build et le snapshot du 28 juillet avant toute restitution au staff.",
    )

    # Tableau des objectifs et état des preuves Bloc 2.
    objectives = doc.tables[0]
    set_cell(
        objectives.rows[3].cells[2],
        "Snapshot JSON horodaté le 28 juillet 2026 à 00 h 01 UTC, résultats Spearman et Mann-Whitney archivés dans analysis/results",
    )
    set_cell(
        objectives.rows[4].cells[2],
        "Dashboards alimentés par le snapshot. Protocole de lecture en moins de deux minutes prêt, test avec le staff Nexus non encore exécuté",
    )
    set_cell(
        objectives.rows[5].cells[2],
        "Documentation par public et support de formation de 45 minutes disponibles. Session Nexus non encore réalisée",
    )

    milestones = doc.tables[1]
    set_cell(milestones.rows[3].cells[4], "Premier commit et structure du dépôt versionnés")
    set_cell(milestones.rows[5].cells[4], "18 modèles et 63 tests de données, soit 81 opérations réussies. Workflow CI versionné le 26 juillet")
    set_cell(milestones.rows[6].cells[4], "Snapshot JSON horodaté le 28 juillet 2026 à 00 h 01 UTC")
    set_cell(milestones.rows[7].cells[4], "Dashboards alimentés par le snapshot. Protocole de deux minutes prêt et non encore exécuté avec Nexus")

    audit = doc.tables[2]
    audit_updates = {
        4: "+2, reprises d'ingestion cumulées",
        5: "+3, ajustements d'ingestion avant arbitrage",
        6: "+3, arbitrage ouvert le 22 juillet et correction livrée le 26 juillet",
        7: "+2, validation le 28 juillet en S6 et analyses en avance",
    }
    for row_index, value in audit_updates.items():
        set_cell(audit.rows[row_index].cells[3], value)

    # Le résumé en pourcentages reste lisible, mais le calcul détaillé est bien en annexe 14.
    allocation = doc.tables[4]
    set_cell(allocation.rows[1].cells[2], "21 jours sur 52")
    set_cell(allocation.rows[2].cells[2], "18 jours sur 52")
    set_cell(allocation.rows[3].cells[2], "13 jours sur 52")

    rse = doc.tables[6]
    set_cell(
        rse.rows[2].cells[1],
        "Identifiants dédiés par service, secrets hors dépôt, services non exposés hors du réseau Docker local, workflow CI versionné, sauvegardes et restauration testées",
    )

    phases = doc.tables[7]
    set_cell(phases.rows[2].cells[1], "S2 à S4")
    set_cell(phases.rows[3].cells[1], "S4 et S5")
    set_cell(phases.rows[3].cells[2], "Build dbt complet le 26 juillet, 18 modèles et 63 tests de données, soit 81 opérations réussies")
    set_cell(phases.rows[4].cells[1], "S6")
    set_cell(phases.rows[4].cells[2], "Snapshot JSON horodaté le 28 juillet 2026 à 00 h 01 UTC")
    set_cell(phases.rows[5].cells[1], "S6 à S8")

    watch = doc.tables[13]
    set_cell(watch.rows[8].cells[0], "22 juillet")
    set_cell(watch.rows[8].cells[1], "Revue croisée Leaguepedia et Riot")
    set_cell(watch.rows[8].cells[2], "Écart entre les nomenclatures 26.x et 16.x")
    set_cell(watch.rows[8].cells[3], "Alerte et arbitrage ouverts en S5")
    set_cell(watch.rows[9].cells[0], "26 juillet")
    set_cell(watch.rows[9].cells[1], "Documentation dbt et revue du modèle")
    set_cell(watch.rows[9].cells[2], "Test singulier de recouvrement entre les sources")
    set_cell(watch.rows[9].cells[3], "Normalisation livrée, validation finale en S6 le 28 juillet")

    resources = doc.tables[16]
    set_cell(resources.rows[3].cells[1], "Dépôt de code et workflow CI avec lint, tests unitaires, dbt parse et validation Docker Compose")

    indicators = doc.tables[18]
    set_cell(indicators.rows[3].cells[3], "52 jours pour la phase intensive et 70 jours pour le projet complet")
    set_cell(indicators.rows[4].cells[3], "Build de référence à 81 opérations réussies et workflow CI versionné")

    charge = doc.tables[20]
    set_cell(charge.rows[8].cells[0], "Total de la phase intensive, 52 jours")
    set_cell(charge.rows[8].cells[4], "Répartition calculée de 21, 18 et 13 jours")

    specification = doc.tables[22]
    set_cell(specification.rows[6].cells[2], "Build vert avec 18 modèles et 63 tests de données, soit 81 opérations réussies")
    set_cell(specification.rows[7].cells[2], "Snapshot JSON horodaté le 28 juillet 2026 à 00 h 01 UTC et versionné")


def move_audit_to_annex(doc: Document) -> None:
    audit = doc.tables[2]
    indicators = doc.tables[18]
    audit._tbl.getparent().remove(audit._tbl)
    move_after(audit._tbl, indicators._tbl)

    annex_12 = heading_starting(doc, "Annexe 12 : indicateurs de pilotage")
    note = OxmlElement("w:p")
    p_pr = OxmlElement("w:pPr")
    note.append(p_pr)
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = "Piste d'audit hebdomadaire. Le cumul inclut les 18 jours de l'amont et l'écart porte sur la phase intensive."
    run.append(text)
    note.append(run)
    indicators._tbl.addnext(note)
    # Le déplacement XML place le tableau après la note.
    note.addnext(audit._tbl)

    annex_12.paragraph_format.keep_with_next = True


def paginate_annexes(doc: Document) -> None:
    introduction = heading_starting(doc, "Introduction")
    set_page_break_before(introduction)

    rse_actions = heading_starting(doc, "3. Plan d'actions")
    set_page_break_before(rse_actions)

    annexes_heading = heading_starting(doc, "Annexes")
    set_page_break_before(annexes_heading)
    for number in range(1, 16):
        heading = heading_starting(doc, f"Annexe {number} :")
        set_page_break_before(heading)
        heading.paragraph_format.keep_with_next = True


def main() -> None:
    doc = Document(SOURCE)
    remove_existing_toc_field(doc)
    apply_content_corrections(doc)
    move_audit_to_annex(doc)
    replace_toc(doc, None)
    paginate_annexes(doc)
    sanitize_visible_text(doc)
    style_document(doc)

    doc.core_properties.title = "MyLeague - Dossier Bloc 3 final"
    doc.core_properties.subject = "Élaborer et piloter un projet data"
    doc.core_properties.comments = "Version harmonisée avec le Bloc 2 et la grille d'évaluation"
    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
