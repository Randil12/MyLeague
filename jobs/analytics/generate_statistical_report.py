"""Tests statistiques du Bloc 2 (C2.1.4), exécutés sur l'entrepôt.

Deux tests, conformes à la méthodologie du dossier (α = 5 %, bilatéraux) :
  1. Spearman : association monotone entre présence solo queue et présence
     professionnelle, par champion, sur un patch donné.
  2. Mann-Whitney : |Δ winrate| entre deux patchs, champions officiellement
     modifiés (notes de patch) contre groupe de contrôle.

Sortie : valeurs n, statistique, p, décision + lignes prêtes à coller dans
le dossier (tableau d'interprétation et annexe 1). Un fichier récapitulatif
est écrit dans artifacts/ (monté dans le conteneur Airflow).

Usage :
    docker exec myleague-airflow python -m jobs.analytics.generate_statistical_report
    docker exec myleague-airflow python -m jobs.analytics.generate_statistical_report --patch 16.14 --prev-patch 16.13
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

ALPHA = 0.05


def get_conn():
    import psycopg2

    return psycopg2.connect(
        host=os.getenv("GOLD_POSTGRES_HOST", "gold-postgres"),
        port=int(os.getenv("GOLD_POSTGRES_PORT", "5432")),
        dbname=os.getenv("GOLD_POSTGRES_DB", "gold"),
        user=os.getenv("GOLD_POSTGRES_USER", "gold"),
        password=os.getenv("GOLD_POSTGRES_PASSWORD", "gold"),
    )


def format_p(p: float) -> str:
    """Formatage du dossier : p < 0,001 en dessous du millième, sinon 3 décimales."""
    if p < 0.001:
        return "p < 0,001"
    return f"p = {p:.3f}".replace(".", ",")


def decision(p: float, alpha: float = ALPHA) -> str:
    return "H0 rejetée" if p < alpha else "H0 non rejetée"


def fetch_all(conn, sql: str, params: tuple) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def latest_patches(conn) -> list[str]:
    rows = fetch_all(conn, "SELECT patch FROM gold.gold_patch_summary ORDER BY patch DESC", ())
    return [r[0] for r in rows]


def test_spearman_solo_pro(conn, patch: str, min_picks: int) -> dict:
    rows = fetch_all(
        conn,
        """
        SELECT s.champion_name, s.presence, p.presence
        FROM gold.gold_champion_bans_by_patch s
        JOIN gold.gold_pro_champion_draft_by_patch p
          ON p.patch = s.patch AND p.champion_name = s.champion_name
        WHERE s.patch = %s
          AND s.picks >= %s
          AND (p.picks + p.bans) > 0
        """,
        (patch, min_picks),
    )
    n = len(rows)
    result = {"n": n, "patch": patch}
    if n < 10:
        result["error"] = (
            f"Échantillon insuffisant ({n} champions communs, minimum conseillé : 10). "
            "Vérifier que leaguepedia_ingestion et dbt_transform ont tourné sur ce patch."
        )
        return result

    from scipy.stats import spearmanr

    solo = [float(r[1]) for r in rows]
    pro = [float(r[2]) for r in rows]
    rho, p = spearmanr(solo, pro)
    result.update({"rho": rho, "p": p, "decision": decision(p)})
    return result


def test_mannwhitney_patch(conn, patch: str, prev_patch: str, min_picks: int) -> dict:
    rows = fetch_all(
        conn,
        """
        WITH cur AS (
            SELECT champion_name, winrate FROM gold.gold_champion_meta_by_patch
            WHERE patch = %s AND picks >= %s
        ),
        prev AS (
            SELECT champion_name, winrate FROM gold.gold_champion_meta_by_patch
            WHERE patch = %s AND picks >= %s
        ),
        modified AS (
            SELECT DISTINCT champion_name FROM gold.gold_champion_patch_changes
            WHERE patch = %s
        )
        SELECT cur.champion_name,
               abs(cur.winrate - prev.winrate) AS delta_abs,
               (m.champion_name IS NOT NULL)   AS is_modified
        FROM cur
        JOIN prev USING (champion_name)
        LEFT JOIN modified m USING (champion_name)
        """,
        (patch, min_picks, prev_patch, min_picks, patch),
    )
    modified = [float(r[1]) for r in rows if r[2]]
    control = [float(r[1]) for r in rows if not r[2]]
    result = {
        "patch": patch, "prev_patch": prev_patch,
        "n_modified": len(modified), "n_control": len(control),
    }
    if len(modified) < 5 or len(control) < 5:
        result["error"] = (
            f"Groupes insuffisants (modifiés : {len(modified)}, contrôle : {len(control)} ; "
            "minimum conseillé : 5 par groupe). Il faut deux patchs de données et des notes "
            "de patch scrapées pour le patch courant."
        )
        return result

    from scipy.stats import mannwhitneyu

    stat, p = mannwhitneyu(modified, control, alternative="two-sided")
    result.update({"U": stat, "p": p, "decision": decision(p)})
    return result


def interpretation_spearman(r: dict) -> str:
    if "error" in r:
        return r["error"]
    if r["decision"] == "H0 rejetée":
        sens = "positive" if r["rho"] > 0 else "négative"
        return (f"Association monotone {sens} significative entre présence solo queue et "
                "présence professionnelle : les deux signaux se recoupent mais restent à "
                "croiser sans les fusionner.")
    return ("Pas d'association monotone démontrée au seuil de 5 % : les deux environnements "
            "valorisent des champions différents, ce qui justifie de garder les deux "
            "indicateurs séparés dans la préparation de draft.")


def interpretation_mannwhitney(r: dict) -> str:
    if "error" in r:
        return r["error"]
    if r["decision"] == "H0 rejetée":
        return ("Les champions officiellement modifiés présentent une amplitude de variation "
                "du winrate significativement différente du groupe de contrôle : les notes de "
                "patch sont un signal d'alerte fiable pour la préparation.")
    return ("H0 non rejetée : pas de différence démontrée au seuil de 5 % sur cet échantillon. "
            "Ne pas confondre avec une absence d'effet ; poursuivre la collecte et répéter le "
            "test avec un groupe de champions modifiés plus grand.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Tests statistiques du Bloc 2 sur l'entrepôt.")
    parser.add_argument("--patch", default=None, help="Patch analysé (défaut : dernier connu)")
    parser.add_argument("--prev-patch", default=None, help="Patch précédent (défaut : n-1)")
    parser.add_argument("--min-picks", type=int, default=10)
    parser.add_argument("--out-dir", default="/opt/airflow/artifacts")
    args = parser.parse_args()

    conn = get_conn()
    try:
        patches = latest_patches(conn)
        if not patches:
            raise SystemExit("gold.gold_patch_summary est vide : lancer dbt_transform d'abord.")
        patch = args.patch or patches[0]
        prev = args.prev_patch or (patches[patches.index(patch) + 1]
                                   if patch in patches and patches.index(patch) + 1 < len(patches)
                                   else None)

        s = test_spearman_solo_pro(conn, patch, args.min_picks)
        m = (test_mannwhitney_patch(conn, patch, prev, args.min_picks)
             if prev else {"error": "Un seul patch dans l'entrepôt : le test inter-patchs "
                                    "nécessite deux patchs de données.", "patch": patch,
                           "prev_patch": "—", "n_modified": 0, "n_control": 0})
    finally:
        conn.close()

    lines = []
    lines.append(f"# Résultats statistiques — patch {patch} (α = 5 %, tests bilatéraux)\n")

    lines.append("## Test 1 : Spearman présence solo queue / présence professionnelle")
    if "error" in s:
        lines.append(f"NON CALCULABLE : {s['error']}")
    else:
        rho_txt = f"{s['rho']:.2f}".replace(".", ",")
        lines.append(f"n = {s['n']} champions | rho = {rho_txt} | {format_p(s['p'])} | {s['decision']}")
        lines.append(f"Ligne annexe 1 : Spearman solo/pro | n = {s['n']} | rho = {rho_txt} | "
                     f"{format_p(s['p'])} | {s['decision']}")
    lines.append(f"Interprétation métier : {interpretation_spearman(s)}\n")

    lines.append(f"## Test 2 : Mann-Whitney |Δ winrate| ({m.get('prev_patch')} → {patch})")
    if "error" in m:
        lines.append(f"NON CALCULABLE : {m['error']}")
    else:
        lines.append(f"n modifiés = {m['n_modified']} | n contrôle = {m['n_control']} | "
                     f"U = {m['U']:.0f} | {format_p(m['p'])} | {m['decision']}")
        lines.append(f"Ligne annexe 1 : Mann-Whitney patch | n = {m['n_modified']} + {m['n_control']} | "
                     f"U = {m['U']:.0f} | {format_p(m['p'])} | {m['decision']}")
    lines.append(f"Interprétation métier : {interpretation_mannwhitney(m)}\n")

    output = "\n".join(lines)
    print(output)

    out_dir = Path(args.out_dir)
    if out_dir.exists():
        out_file = out_dir / f"generate_statistical_report_patch_{patch.replace('.', '_')}.md"
        out_file.write_text(output, encoding="utf-8")
        print(f"\nRécapitulatif écrit : {out_file}")


if __name__ == "__main__":
    main()
