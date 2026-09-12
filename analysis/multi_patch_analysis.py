"""Analyse multi-patch reproductible pour consolider C2.1.3 et C2.1.4.

Le script lit exclusivement les modèles Gold, calcule :

* la couverture solo queue / professionnelle par patch ;
* une corrélation de Spearman par patch commun ;
* un Mann–Whitney regroupant les observations champion × transition de patch ;
* une taille d'effet rank-bisériale et un intervalle bootstrap descriptif.

Il écrit un snapshot JSON et trois figures directement réutilisables dans le
dossier RNCP.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MPL_CONFIG_DIR = ROOT / ".cache" / "matplotlib"
MPL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CONFIG_DIR))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.engine import URL  # noqa: E402

RESULTS = ROOT / "analysis" / "results" / "multi_patch_analysis_results.json"
ASSETS = ROOT / "docs" / "assets" / "bloc2"
ALPHA = 0.05
MIN_PICKS = 5
BLUE = "#0072B2"
ORANGE = "#E69F00"
GREEN = "#009E73"
GRAY = "#6B7280"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def connect():
    load_dotenv(ROOT / ".env")
    return create_engine(
        URL.create(
            "postgresql+psycopg2",
            username=os.getenv("GOLD_POSTGRES_USER", "gold"),
            password=os.getenv("GOLD_POSTGRES_PASSWORD", "gold"),
            host=os.getenv("ANALYSIS_POSTGRES_HOST", "127.0.0.1"),
            port=int(os.getenv("ANALYSIS_POSTGRES_PORT", "5433")),
            database=os.getenv("GOLD_POSTGRES_DB", "gold"),
        ),
        connect_args={"connect_timeout": 5},
        pool_pre_ping=True,
    )


def query(conn, sql: str, params: tuple | None = None) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn, params=params)


def save_figure(fig: plt.Figure, filename: str) -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    fig.savefig(ASSETS / filename, dpi=190, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def bootstrap_median_difference(
    changed: np.ndarray,
    control: np.ndarray,
    *,
    iterations: int = 5000,
    seed: int = 20260728,
) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    differences = np.empty(iterations)
    for index in range(iterations):
        changed_sample = rng.choice(changed, size=len(changed), replace=True)
        control_sample = rng.choice(control, size=len(control), replace=True)
        differences[index] = np.median(changed_sample) - np.median(control_sample)
    low, high = np.quantile(differences, [0.025, 0.975])
    return float(low), float(high)


def coverage_figure(coverage: pd.DataFrame) -> None:
    shown = coverage.sort_values(["patch_major", "patch_minor"])
    x = np.arange(len(shown))
    width = 0.38
    fig, ax = plt.subplots(figsize=(9.5, 5.5))
    solo = ax.bar(
        x - width / 2,
        shown["solo_matches"],
        width,
        label="Solo queue EUW",
        color=BLUE,
    )
    pro = ax.bar(
        x + width / 2,
        shown["pro_matches"],
        width,
        label="Compétition Leaguepedia",
        color=ORANGE,
    )
    ax.bar_label(solo, padding=3, fontsize=8)
    ax.bar_label(pro, padding=3, fontsize=8)
    ax.set_xticks(x, shown["patch"])
    ax.set_ylabel("Nombre de parties")
    ax.set_title("Couverture analytique par patch")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.2)
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(
        0.01,
        0.01,
        "Solo : parties classées EUW des joueurs suivis. Pro : parties Leaguepedia "
        "dont le patch est renseigné et normalisé.",
        fontsize=8,
        color=GRAY,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    save_figure(fig, "multi_patch_coverage.png")


def spearman_figure(results: list[dict]) -> None:
    valid = [result for result in results if result.get("rho") is not None]
    fig, ax = plt.subplots(figsize=(9, 5.4))
    patches = [result["patch"] for result in valid]
    values = [result["rho"] for result in valid]
    colors = [GREEN if result["p_value"] < ALPHA else GRAY for result in valid]
    bars = ax.bar(patches, values, color=colors, width=0.58)
    ax.bar_label(
        bars,
        labels=[f"ρ={result['rho']:.2f}\nn={result['n']}" for result in valid],
        padding=4,
        fontsize=9,
    )
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_ylim(min(-0.15, min(values, default=0) - 0.15), 1)
    ax.set_ylabel("Corrélation de Spearman (ρ)")
    ax.set_title("Association solo queue / compétition selon le patch")
    ax.grid(axis="y", alpha=0.2)
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(
        0.01,
        0.01,
        "Vert : p < 0,05 ; gris : association non démontrée. Test bilatéral, "
        f"champions avec au moins {MIN_PICKS} picks solo queue.",
        fontsize=8,
        color=GRAY,
    )
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    save_figure(fig, "spearman_by_patch.png")


def patch_effect_figure(observations: pd.DataFrame, test_result: dict) -> None:
    changed = observations.loc[observations["changed"], "absolute_delta"].to_numpy() * 100
    control = observations.loc[~observations["changed"], "absolute_delta"].to_numpy() * 100
    fig, ax = plt.subplots(figsize=(9, 5.8))
    box = ax.boxplot(
        [control, changed],
        tick_labels=["Sans changement officiel", "Avec changement officiel"],
        patch_artist=True,
        showmeans=True,
    )
    box["boxes"][0].set_facecolor(BLUE)
    box["boxes"][1].set_facecolor(ORANGE)
    rng = np.random.default_rng(42)
    for position, values, color in [(1, control, BLUE), (2, changed, ORANGE)]:
        jitter = rng.normal(position, 0.035, size=len(values))
        ax.scatter(jitter, values, s=18, alpha=0.45, color=color, edgecolor="white")
    ax.set_ylabel("|Δ winrate| (points de pourcentage)")
    ax.set_title("Effet observé des changements Riot, toutes transitions disponibles")
    ax.grid(axis="y", alpha=0.2)
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(
        0.01,
        0.01,
        f"Mann–Whitney bilatéral : U={test_result['u_statistic']:.0f}, "
        f"p={test_result['p_value']:.3f}, n modifiés={test_result['n_changed']}, "
        f"n témoins={test_result['n_control']}.",
        fontsize=8.5,
        color=GRAY,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    save_figure(fig, "multi_patch_change_effect.png")


def run() -> dict:
    engine = connect()
    try:
        coverage = query(
            engine,
            """
            with patches as (
                select patch from gold.gold_patch_summary
                union
                select patch from gold.gold_pro_champion_draft_by_patch
            ),
            solo as (
                select patch, max(total_matches) as solo_matches
                from gold.gold_patch_summary group by 1
            ),
            pro as (
                select patch, max(total_games) as pro_matches
                from gold.gold_pro_champion_draft_by_patch group by 1
            )
            select p.patch,
                   coalesce(s.solo_matches, 0)::int as solo_matches,
                   coalesce(r.pro_matches, 0)::int as pro_matches,
                   split_part(p.patch, '.', 1)::int as patch_major,
                   split_part(p.patch, '.', 2)::int as patch_minor
            from patches p
            left join solo s using (patch)
            left join pro r using (patch)
            where p.patch ~ '^[0-9]+[.][0-9]+$'
            order by patch_major, patch_minor
            """,
        )
        joined = query(
            engine,
            """
            select s.patch, s.champion_name,
                   s.presence::float as solo_presence,
                   p.presence::float as pro_presence,
                   s.picks, p.total_games
            from gold.gold_champion_bans_by_patch s
            inner join gold.gold_pro_champion_draft_by_patch p
                using (patch, champion_name)
            where s.picks >= %s
            """,
            (MIN_PICKS,),
        )
        observations = query(
            engine,
            """
            select patch, previous_patch, champion_name,
                   abs(winrate_delta)::float as absolute_delta,
                   official_change is not null as changed,
                   picks, previous_picks
            from gold.gold_champion_patch_evolution
            where previous_patch is not null
              and picks >= %s
              and previous_picks >= %s
            """,
            (MIN_PICKS, MIN_PICKS),
        )
        changes_by_patch = query(
            engine,
            """
            select patch, count(distinct champion_name)::int as changed_champions
            from gold.gold_champion_patch_changes
            group by 1 order by 1
            """,
        )
    finally:
        engine.dispose()

    spearman_results: list[dict] = []
    for patch, frame in joined.groupby("patch", sort=True):
        if len(frame) < 5:
            spearman_results.append({"patch": patch, "n": len(frame), "status": "insufficient"})
            continue
        rho, p_value = stats.spearmanr(frame["solo_presence"], frame["pro_presence"])
        spearman_results.append(
            {
                "patch": str(patch),
                "n": int(len(frame)),
                "rho": round(float(rho), 6),
                "p_value": round(float(p_value), 10),
                "decision": "H0 rejetée" if p_value < ALPHA else "H0 non rejetée",
            }
        )

    changed = observations.loc[observations["changed"], "absolute_delta"].to_numpy(dtype=float)
    control = observations.loc[~observations["changed"], "absolute_delta"].to_numpy(dtype=float)
    if len(changed) >= 3 and len(control) >= 3:
        mann = stats.mannwhitneyu(changed, control, alternative="two-sided", method="auto")
        rank_biserial = 2 * float(mann.statistic) / (len(changed) * len(control)) - 1
        ci_low, ci_high = bootstrap_median_difference(changed, control)
        mann_result = {
            "n_changed": int(len(changed)),
            "n_control": int(len(control)),
            "median_changed": round(float(np.median(changed)), 6),
            "median_control": round(float(np.median(control)), 6),
            "median_difference": round(float(np.median(changed) - np.median(control)), 6),
            "median_difference_bootstrap_ci95": [round(ci_low, 6), round(ci_high, 6)],
            "u_statistic": round(float(mann.statistic), 6),
            "p_value": round(float(mann.pvalue), 10),
            "rank_biserial": round(rank_biserial, 6),
            "decision": "H0 rejetée" if mann.pvalue < ALPHA else "H0 non rejetée",
        }
    else:
        mann_result = {
            "n_changed": int(len(changed)),
            "n_control": int(len(control)),
            "status": "insufficient",
            "decision": "Test non calculable : moins de trois observations dans un groupe.",
        }

    coverage_figure(coverage)
    if any(result.get("rho") is not None for result in spearman_results):
        spearman_figure(spearman_results)
    if "u_statistic" in mann_result:
        patch_effect_figure(observations, mann_result)

    result = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source": "PostgreSQL Gold — MyLeague",
        "alpha": ALPHA,
        "minimum_picks_per_patch": MIN_PICKS,
        "coverage": coverage.drop(columns=["patch_major", "patch_minor"]).to_dict(
            orient="records"
        ),
        "patch_changes": changes_by_patch.to_dict(orient="records"),
        "spearman_by_patch": spearman_results,
        "mann_whitney_pooled_transitions": mann_result,
        "limitations": [
            "Les parties solo queue proviennent de joueurs suivis sur EUW et non d'un tirage aléatoire.",
            "Les parties professionnelles Leaguepedia couvrent plusieurs compétitions mondiales.",
            "Une même identité de champion peut apparaître sur plusieurs transitions de patch.",
            "L'intervalle bootstrap décrit la stabilité de la médiane observée, pas une causalité.",
            "Les résultats restent exploratoires et doivent être complétés par l'expertise du staff.",
        ],
    }
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return result


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, default=str))
