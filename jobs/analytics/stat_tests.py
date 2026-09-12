"""Tests statistiques du Bloc 2 (C2.1.4) : calcule n, statistiques, valeurs p et décisions.

Reproduit exactement la méthodologie du dossier :
  Test 1 : corrélation de Spearman bilatérale entre la presence solo queue et la
           presence professionnelle, par champion, sur le patch sélectionné.
           H0 : pas d'association monotone (rho = 0). Seuil : 5 %.
  Test 2 : Mann-Whitney bilatéral sur |delta winrate| entre deux patchs, groupe
           "modifié" (champions cités dans les notes de patch) vs contrôle.
           H0 : distributions identiques. Seuil : 5 %.

Usage (depuis le conteneur Airflow, scipy y est disponible via scikit-learn) :
    docker exec myleague-airflow python /opt/airflow/jobs/analytics/stat_tests.py
    docker exec myleague-airflow python /opt/airflow/jobs/analytics/stat_tests.py \
        --patch 16.14 --previous 16.13 --min-picks 10

La sortie est prête à coller dans les tableaux du dossier (n, statistique, p,
décision, date d'extraction).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from jobs.riot.euw_ingest import get_gold_conn

ALPHA = 0.05


def fetch_df(conn, sql: str, params: tuple = ()) -> "pandas.DataFrame":  # noqa: F821
    import pandas as pd

    return pd.read_sql(sql, conn, params=params)


def latest_patches(conn) -> list[str]:
    df = fetch_df(conn, "SELECT patch FROM gold.gold_patch_summary ORDER BY patch DESC")
    return df["patch"].tolist()


def test_spearman_solo_pro(conn, patch: str, min_picks: int) -> dict:
    """Presence solo queue vs presence professionnelle, par champion."""
    from scipy import stats

    df = fetch_df(
        conn,
        """
        SELECT s.champion_name,
               s.presence      AS presence_solo,
               p.presence      AS presence_pro,
               s.picks         AS picks_solo,
               p.total_games   AS games_pro
        FROM gold.gold_champion_bans_by_patch s
        JOIN gold.gold_pro_champion_draft_by_patch p
          ON p.patch = s.patch AND p.champion_name = s.champion_name
        WHERE s.patch = %s
          AND s.picks >= %s
        """,
        (patch, min_picks),
    )

    result = {
        "test": "Spearman bilatéral (presence solo queue vs presence pro)",
        "patch": patch,
        "n": len(df),
        "seuil_picks": min_picks,
    }
    if len(df) < 5:
        result["statut"] = (
            f"Échantillon insuffisant ({len(df)} champions communs aux deux sources). "
            "Vérifier que leaguepedia_ingestion et dbt_transform ont tourné sur ce patch."
        )
        return result

    rho, p_value = stats.spearmanr(df["presence_solo"], df["presence_pro"])
    result.update(
        rho=round(float(rho), 3),
        p=round(float(p_value), 4),
        decision="Rejet de H0 : association monotone significative"
        if p_value < ALPHA
        else "H0 non rejetée : pas d'association démontrée",
        sens="positive" if rho > 0 else "négative",
    )
    return result


def test_mannwhitney_patch(conn, patch: str, previous: str, min_picks: int) -> dict:
    """|delta winrate| entre deux patchs : champions modifiés vs groupe de contrôle."""
    from scipy import stats

    df = fetch_df(
        conn,
        """
        WITH cur AS (
            SELECT champion_name, winrate, picks
            FROM gold.gold_champion_meta_by_patch WHERE patch = %s AND picks >= %s
        ),
        prev AS (
            SELECT champion_name, winrate, picks
            FROM gold.gold_champion_meta_by_patch WHERE patch = %s AND picks >= %s
        ),
        modified AS (
            SELECT DISTINCT champion_name
            FROM gold.gold_champion_patch_changes WHERE patch = %s
        )
        SELECT cur.champion_name,
               abs(cur.winrate - prev.winrate)                  AS delta_abs,
               (m.champion_name IS NOT NULL)                    AS est_modifie
        FROM cur
        JOIN prev USING (champion_name)
        LEFT JOIN modified m USING (champion_name)
        """,
        (patch, min_picks, previous, min_picks, patch),
    )

    modified = df[df["est_modifie"]]["delta_abs"]
    control = df[~df["est_modifie"]]["delta_abs"]

    result = {
        "test": "Mann-Whitney bilatéral (|delta winrate| modifiés vs non modifiés)",
        "patchs": f"{previous} -> {patch}",
        "n_modifies": len(modified),
        "n_controle": len(control),
        "seuil_picks": min_picks,
    }
    if len(modified) < 3 or len(control) < 3:
        result["statut"] = (
            f"Groupes insuffisants (modifiés={len(modified)}, contrôle={len(control)}). "
            "Il faut deux patchs de données (allonger RIOT_EUW_LOOKBACK_DAYS) et des "
            "notes de patch ingérées pour ce patch (patch_notes_scraping)."
        )
        return result

    u_stat, p_value = stats.mannwhitneyu(modified, control, alternative="two-sided")
    result.update(
        U=round(float(u_stat), 1),
        p=round(float(p_value), 4),
        mediane_modifies=round(float(modified.median()), 4),
        mediane_controle=round(float(control.median()), 4),
        decision="Rejet de H0 : amplitudes de variation différentes"
        if p_value < ALPHA
        else "H0 non rejetée : pas de différence démontrée",
    )
    return result


def print_result(result: dict) -> None:
    print("-" * 78)
    for key, value in result.items():
        print(f"  {key:<20} : {value}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Tests statistiques du Bloc 2 (C2.1.4).")
    parser.add_argument("--patch", default=None, help="Patch analysé (défaut : le plus récent)")
    parser.add_argument("--previous", default=None, help="Patch précédent (défaut : auto)")
    parser.add_argument("--min-picks", type=int, default=10)
    args = parser.parse_args()

    conn = get_gold_conn()
    try:
        patches = latest_patches(conn)
        if not patches:
            print("Aucun patch dans gold.gold_patch_summary : lancer les DAGs d'abord.")
            return

        patch = args.patch or patches[0]
        previous = args.previous or (patches[1] if len(patches) > 1 else None)

        extraction = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        print(f"\n=== Tests statistiques MyLeague — extraction du {extraction} ===")
        print(f"Seuil de significativité : {ALPHA:.0%} — tests bilatéraux")

        print_result(test_spearman_solo_pro(conn, patch, args.min_picks))

        if previous is None:
            print("-" * 78)
            print("  Test Mann-Whitney : un seul patch en entrepôt, comparaison impossible.")
            print("  Allonger la fenêtre de collecte (RIOT_EUW_LOOKBACK_DAYS=30) pour")
            print("  couvrir le patch précédent, puis relancer riot_euw_ingestion et dbt.")
        else:
            print_result(test_mannwhitney_patch(conn, patch, previous, args.min_picks))
        print("-" * 78)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
