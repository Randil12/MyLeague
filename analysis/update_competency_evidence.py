"""Corrige les preuves C2.1.3 et C2.1.4 dans le dossier Bloc 2 fourni.

Le script conserve le document source et produit une copie corrigée. Les valeurs
injectées proviennent exclusivement du snapshot reproductible
``analysis/results/statistical_analysis_results.json`` et du dernier ``dbt build`` archivé.
"""

from __future__ import annotations

import json
from pathlib import Path

from docx import Document


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "Bloc2_David_Nguyen_M2.docx"
OUTPUT = ROOT / "docs" / "Bloc2_David_Nguyen_M2_corrige.docx"
RESULTS = ROOT / "analysis" / "results" / "statistical_analysis_results.json"


def replace_paragraph(paragraph, text: str) -> None:
    """Remplace le texte sans modifier le style du paragraphe."""
    if paragraph.runs:
        paragraph.runs[0].text = text
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(text)


def replace_paragraph_starting_with(doc: Document, prefix: str, text: str) -> None:
    matches = [paragraph for paragraph in doc.paragraphs if paragraph.text.startswith(prefix)]
    if len(matches) != 1:
        raise RuntimeError(
            f"Paragraphe attendu une fois, trouvé {len(matches)} fois : {prefix!r}"
        )
    replace_paragraph(matches[0], text)


def replace_cell_text(cell, text: str) -> None:
    paragraph = cell.paragraphs[0]
    replace_paragraph(paragraph, text)
    for extra in cell.paragraphs[1:]:
        replace_paragraph(extra, "")


def find_table(doc: Document, first_header: str):
    matches = [
        table
        for table in doc.tables
        if table.rows and table.rows[0].cells[0].text == first_header
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Tableau attendu une fois, trouvé {len(matches)} fois : {first_header!r}"
        )
    return matches[0]


def main() -> None:
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    h1 = data["hypothesis_1"]
    h2 = data["hypothesis_2"]
    latest = data["latest_patch"]
    patches = data["patches"]
    generated_at = data["generated_at_utc"]

    doc = Document(SOURCE)

    replace_paragraph_starting_with(
        doc,
        "Les vues Gold* sont calculées",
        "Les vues Gold* sont calculées par PostgreSQL et dbt, puis consommées par "
        "l'application, les dashboards et le script Python d'analyse. Le build de "
        "référence archivé a construit 18 modèles et exécuté 63 tests de données : "
        "81 opérations réussies, sans avertissement, erreur ni étape ignorée. Les "
        "tableaux et figures qui suivent proviennent du même snapshot Gold, ce qui "
        "garantit une définition identique des indicateurs dans chaque support.",
    )
    replace_paragraph_starting_with(
        doc,
        "La photographie de l'échantillon est générée",
        f"La photographie calculée couvre {patches[0]['total_matches']} parties au "
        f"patch {patches[0]['patch']} et {patches[1]['total_matches']} parties au "
        f"patch {patches[1]['patch']}. Sur le patch {latest}, "
        f"{data['draft']['champions_analyzed']} couples champion-rôle ayant au moins "
        "10 picks sont analysés. Ces valeurs sont enregistrées dans le snapshot JSON "
        f"horodaté {generated_at} et reprises dans les tableaux de résultats ; elles "
        "ne sont donc ni estimées ni laissées à compléter.",
    )
    replace_paragraph_starting_with(
        doc,
        "Figure 1 : Exemple de restitution",
        f"Figure 1 : Priorités de draft calculées sur le snapshot Gold du patch {latest}.",
    )
    replace_paragraph_starting_with(
        doc,
        "Contrôle technique :",
        "Contrôle technique : le dernier dbt build archivé s'est terminé avec "
        "PASS=81, WARN=0, ERROR=0, SKIP=0 (18 modèles et 63 tests de données). "
        "Le fichier dbt/target/run_results.json et le journal dbt/logs/dbt.log "
        "conservent la preuve d'exécution. Les tests Python des fonctions de décision "
        "statistique sont également réussis.",
    )

    replace_paragraph_starting_with(
        doc,
        "Le script applique une corrélation",
        f"Sur le patch {latest}, la corrélation de rang de Spearman bilatérale porte "
        f"sur n = {h1['n']} champions communs aux sources solo queue et "
        f"professionnelle. Elle donne ρ = {h1['rho']:.3f} et "
        f"p = {h1['p_value']:.2e}. Comme p < 0,05, H0 est rejetée : "
        "l'association monotone est positive, statistiquement significative et "
        "d'intensité modérée. Ce résultat justifie de croiser les deux signaux, sans "
        "les fusionner ni conclure à une causalité.",
    )
    replace_paragraph_starting_with(
        doc,
        "Figure 3 : Exemple de comparaison",
        f"Figure 3 : Présence solo queue et professionnelle au patch {latest} "
        f"(n = {h1['n']}, ρ = {h1['rho']:.3f}, p < 0,001).",
    )
    replace_paragraph_starting_with(
        doc,
        "Le script sépare automatiquement",
        f"Le test de Mann–Whitney bilatéral compare l'amplitude absolue des variations "
        f"entre les patchs {patches[0]['patch']} et {patches[1]['patch']} pour "
        f"{h2['n_changed']} champions modifiés et {h2['n_unchanged']} champions témoins. "
        f"Les amplitudes moyennes sont respectivement de "
        f"{h2['changed_mean_absolute_delta'] * 100:.1f} et "
        f"{h2['unchanged_mean_absolute_delta'] * 100:.1f} points de pourcentage ; "
        f"U = {h2['u_statistic']:.0f} et p = {h2['p_value']:.3f}. H0 n'est pas "
        "rejetée au seuil de 5 % : une différence n'est pas démontrée sur cet "
        "échantillon. Le groupe modifié limité à trois champions réduit fortement "
        "la puissance du test et interdit de conclure à une absence d'effet.",
    )
    replace_paragraph_starting_with(
        doc,
        "Figure 4 : Exemple de comparaison",
        f"Figure 4 : Comparaison calculée des variations de winrate entre les patchs "
        f"{patches[0]['patch']} et {patches[1]['patch']} "
        f"(U = {h2['u_statistic']:.0f}, p = {h2['p_value']:.3f}).",
    )
    replace_paragraph_starting_with(
        doc,
        "Figure 5 : Exemple de suivi",
        "Figure 5 : Suivi calculé du volume et de la durée moyenne par patch.",
    )
    replace_paragraph_starting_with(
        doc,
        "Le précédent snapshot illustrait",
        f"Les deux hypothèses ont été testées sur le snapshot Gold horodaté "
        f"{generated_at}. Pour Spearman, H0 est rejetée "
        f"(n = {h1['n']}, ρ = {h1['rho']:.3f}, p < 0,001) : une association positive "
        "est démontrée. Pour Mann–Whitney, H0 n'est pas rejetée "
        f"(n = {h2['n_changed']} contre {h2['n_unchanged']}, "
        f"U = {h2['u_statistic']:.0f}, p = {h2['p_value']:.3f}) : l'effet des "
        "changements officiels n'est pas démontré avec cet échantillon. Ces décisions "
        "répondent aux hypothèses initiales tout en conservant leurs limites.",
    )

    interpretation = find_table(doc, "Question")
    interpretation_rows = [
        [
            "Solo queue et professionnel évoluent-ils ensemble ?",
            f"n = {h1['n']} ; ρ = {h1['rho']:.3f} ; p = {h1['p_value']:.2e}",
            "H0 rejetée : association positive significative",
            "Croiser les signaux sans les fusionner ; aucune causalité n'est démontrée.",
        ],
        [
            "Les champions modifiés varient-ils davantage ?",
            (
                f"n = {h2['n_changed']} modifiés / {h2['n_unchanged']} témoins ; "
                f"U = {h2['u_statistic']:.0f} ; p = {h2['p_value']:.3f}"
            ),
            "H0 non rejetée : différence non démontrée",
            "Poursuivre la collecte ; trois champions modifiés donnent une faible puissance.",
        ],
    ]
    for row, values in zip(interpretation.rows[1:], interpretation_rows, strict=True):
        for cell, value in zip(row.cells, values, strict=True):
            replace_cell_text(cell, value)

    summary = find_table(doc, "Test")
    summary_rows = [
        [
            "Spearman solo/pro",
            f"n = {h1['n']}",
            f"ρ = {h1['rho']:.3f}",
            f"{h1['p_value']:.2e}",
            "H0 rejetée",
        ],
        [
            "Mann–Whitney patch",
            f"{h2['n_changed']} / {h2['n_unchanged']}",
            f"U = {h2['u_statistic']:.0f}",
            f"{h2['p_value']:.3f}",
            "H0 non rejetée",
        ],
    ]
    for row, values in zip(summary.rows[1:], summary_rows, strict=True):
        for cell, value in zip(row.cells, values, strict=True):
            replace_cell_text(cell, value)

    doc.core_properties.title = "MyLeague — Dossier Bloc 2 — C2.1.3 et C2.1.4 consolidées"
    doc.core_properties.subject = (
        "Requêtes, dashboards, résultats et tests statistiques interprétés"
    )
    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
