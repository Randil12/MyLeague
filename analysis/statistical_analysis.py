"""Analyse statistique reproductible et figures du dossier RNCP Bloc 2."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MPL_CONFIG_DIR = ROOT / ".cache" / "matplotlib"
MPL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CONFIG_DIR))

import matplotlib  # noqa: E402 - le cache doit être configuré avant l'import

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.engine import URL  # noqa: E402

RESULTS_DIR = ROOT / "analysis" / "results"
ASSETS_DIR = ROOT / "docs" / "assets" / "bloc2"
MIN_PICKS = 5
ALPHA = 0.05

BLUE = "#0072B2"
ORANGE = "#E69F00"
GREEN = "#009E73"
PURPLE = "#CC79A7"
GRAY = "#6B7280"


def load_dotenv(path: Path) -> None:
    """Charge le fichier .env sans écraser l'environnement courant."""
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
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        ASSETS_DIR / filename,
        dpi=180,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close(fig)


def draft_figure(draft: pd.DataFrame, patch: str) -> None:
    shown = draft.head(12).sort_values("priority_score")
    colors = [BLUE if value >= 30 else ORANGE for value in shown["priority_score"]]
    fig, ax = plt.subplots(figsize=(10.5, 6.2))
    bars = ax.barh(shown["champion_name"], shown["priority_score"], color=colors)
    ax.bar_label(bars, fmt="%.1f", padding=4, fontsize=9)
    ax.set_title(f"Priorités de draft explicables: patch {patch}")
    ax.set_xlabel("Score de priorité (0–100)")
    ax.set_xlim(0, max(65, float(shown["priority_score"].max()) + 8))
    ax.grid(axis="x", alpha=0.2)
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(
        0.01,
        0.01,
        "Bleu : score ≥ 30 ; orange : score < 30. Tous les résultats restent "
        "conditionnés par le niveau de confiance affiché dans l'application.",
        fontsize=8,
        color=GRAY,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    save_figure(fig, "draft_priorities.png")


def presence_figure(joined: pd.DataFrame, patch: str, rho: float, p_value: float) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 6.5))
    ax.scatter(
        joined["solo_presence"] * 100,
        joined["pro_presence"] * 100,
        alpha=0.68,
        color=BLUE,
        edgecolor="white",
        linewidth=0.4,
    )
    x = joined["solo_presence"].to_numpy(dtype=float) * 100
    y = joined["pro_presence"].to_numpy(dtype=float) * 100
    slope, intercept = np.polyfit(x, y, 1)
    x_line = np.linspace(x.min(), x.max(), 100)
    ax.plot(x_line, slope * x_line + intercept, color=ORANGE, linewidth=2)
    for _, row in joined.nlargest(7, "pro_presence").iterrows():
        ax.annotate(
            row["champion_name"],
            (row["solo_presence"] * 100, row["pro_presence"] * 100),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8,
        )
    ax.set_title(f"Présence solo queue et professionnelle: patch {patch}")
    ax.set_xlabel("Présence solo queue (%)")
    ax.set_ylabel("Présence professionnelle (%)")
    ax.grid(alpha=0.2)
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(
        0.01,
        0.01,
        f"Corrélation de Spearman : ρ = {rho:.3f}, p = {p_value:.4f}, "
        f"n = {len(joined)} champions (minimum {MIN_PICKS} picks solo queue).",
        fontsize=9,
        color=GRAY,
    )
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    save_figure(fig, "solo_vs_pro_presence.png")


def patch_change_figure(
    changed: pd.Series,
    unchanged: pd.Series,
    previous_patch: str,
    patch: str,
    p_value: float,
) -> None:
    fig, ax = plt.subplots(figsize=(8.3, 5.6))
    boxes = ax.boxplot(
        [unchanged * 100, changed * 100],
        tick_labels=["Sans changement officiel", "Avec changement officiel"],
        patch_artist=True,
        showmeans=True,
    )
    boxes["boxes"][0].set_facecolor(BLUE)
    boxes["boxes"][1].set_facecolor(ORANGE)
    for median in boxes["medians"]:
        median.set_color("black")
    ax.set_title(f"Amplitude des variations de winrate: transition {previous_patch} vers {patch}")
    ax.set_ylabel("|Δ winrate| (points de pourcentage)")
    ax.grid(axis="y", alpha=0.2)
    ax.spines[["top", "right"]].set_visible(False)
    fig.text(
        0.01,
        0.01,
        f"Mann–Whitney bilatéral : p = {p_value:.4f}. "
        f"n changements = {len(changed)}, n contrôle = {len(unchanged)} ; "
        f"minimum {MIN_PICKS} picks sur chacun des deux patchs.",
        fontsize=8.5,
        color=GRAY,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    save_figure(fig, "patch_change_effect.png")


def evolution_figure(evolution: pd.DataFrame, patch: str) -> None:
    shown = evolution.nlargest(12, "absolute_delta").sort_values("winrate_delta")
    colors = [ORANGE if value < 0 else GREEN for value in shown["winrate_delta"]]
    fig, ax = plt.subplots(figsize=(10.5, 6.2))
    bars = ax.barh(shown["champion_name"], shown["winrate_delta"] * 100, color=colors)
    labels = [f"{value * 100:+.1f}" for value in shown["winrate_delta"]]
    ax.bar_label(bars, labels=labels, padding=3, fontsize=8)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_title(f"Principales évolutions de winrate: patch {patch}")
    ax.set_xlabel("Variation par rapport au patch précédent (points)")
    ax.grid(axis="x", alpha=0.2)
    ax.spines[["top", "right"]].set_visible(False)
    for idx, row in shown.reset_index(drop=True).iterrows():
        if row["changed"]:
            ax.text(
                ax.get_xlim()[1] * 0.96,
                idx,
                "note de patch",
                ha="right",
                va="center",
                fontsize=7.5,
                color=PURPLE,
            )
    fig.text(
        0.01,
        0.01,
        f"Champions avec au moins {MIN_PICKS} picks sur les deux patchs. "
        "Orange : baisse ; vert : hausse ; libellé violet : changement officiel identifié.",
        fontsize=8,
        color=GRAY,
    )
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    save_figure(fig, "patch_evolution.png")


def run() -> dict:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    engine = connect()
    try:
        latest_patch = str(
            query(engine, "select max(patch) as patch from gold.gold_patch_summary").iloc[0][
                "patch"
            ]
        )
        patch_summary = query(
            engine,
            """
            select patch, total_matches, avg_duration_min
            from gold.gold_patch_summary
            order by patch
            """,
        )
        previous_patch = str(patch_summary.iloc[-2]["patch"] )
        draft = query(
            engine,
            """
            select champion_name, role, priority_score, confidence_level,
                   recommendation, picks, winrate, presence, pro_presence
            from gold.gold_draft_recommendations
            where patch = %s and picks >= 10
            order by priority_score desc
            """,
            (latest_patch,),
        )
        joined = query(
            engine,
            """
            select s.champion_name, s.presence as solo_presence,
                   p.presence as pro_presence, s.picks, p.total_games
            from gold.gold_champion_bans_by_patch s
            inner join gold.gold_pro_champion_draft_by_patch p
                using (patch, champion_name)
            where s.patch = %s and s.picks >= %s
            """,
            (latest_patch, MIN_PICKS),
        )
        evolution = query(
            engine,
            """
            select champion_name, picks, previous_picks, winrate_delta,
                   abs(winrate_delta) as absolute_delta,
                   official_change is not null as changed
            from gold.gold_champion_patch_evolution
            where patch = %s
              and previous_winrate is not null
              and picks >= %s
              and previous_picks >= %s
            """,
            (latest_patch, MIN_PICKS, MIN_PICKS),
        )
    finally:
        engine.dispose()

    rho, spearman_p = stats.spearmanr(
        joined["solo_presence"],
        joined["pro_presence"],
        nan_policy="omit",
    )
    changed = evolution.loc[evolution["changed"], "absolute_delta"].astype(float)
    unchanged = evolution.loc[~evolution["changed"], "absolute_delta"].astype(float)
    mann_whitney = stats.mannwhitneyu(
        changed,
        unchanged,
        alternative="two-sided",
        method="auto",
    )

    draft_figure(draft, latest_patch)
    presence_figure(joined, latest_patch, float(rho), float(spearman_p))
    patch_change_figure(
        changed, unchanged, previous_patch, latest_patch, float(mann_whitney.pvalue)
    )
    evolution_figure(evolution, latest_patch)

    results = {
        "generated_from": "PostgreSQL gold — MyLeague",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "latest_patch": latest_patch,
        "alpha": ALPHA,
        "minimum_picks_per_patch": MIN_PICKS,
        "patches": patch_summary.to_dict(orient="records"),
        "draft": {
            "champions_analyzed": int(len(draft)),
            "top_recommendations": json.loads(
                draft.head(10).to_json(orient="records")
            ),
        },
        "hypothesis_1": {
            "question": "La présence professionnelle est-elle positivement associée à la présence solo queue ?",
            "null_hypothesis": "Il n'existe pas d'association monotone entre les deux présences.",
            "test": "Corrélation de rang de Spearman, bilatérale",
            "n": int(len(joined)),
            "rho": round(float(rho), 6),
            "p_value": round(float(spearman_p), 8),
            "decision": (
                "Rejet de H0 : association statistiquement significative."
                if spearman_p < ALPHA
                else "H0 non rejetée : association non démontrée sur cet échantillon."
            ),
        },
        "hypothesis_2": {
            "question": (
                "Les champions modifiés officiellement présentent-ils une amplitude "
                "de variation du winrate différente des autres champions ?"
            ),
            "null_hypothesis": "Les distributions de |Δ winrate| sont identiques.",
            "test": "Mann–Whitney U bilatéral",
            "n_changed": int(len(changed)),
            "n_unchanged": int(len(unchanged)),
            "changed_mean_absolute_delta": round(float(changed.mean()), 6),
            "unchanged_mean_absolute_delta": round(float(unchanged.mean()), 6),
            "u_statistic": round(float(mann_whitney.statistic), 6),
            "p_value": round(float(mann_whitney.pvalue), 8),
            "decision": (
                "Rejet de H0 : différence statistiquement significative."
                if mann_whitney.pvalue < ALPHA
                else (
                    "H0 non rejetée : effet non démontré. Le faible nombre de champions "
                    "modifiés impose de poursuivre la collecte."
                )
            ),
        },
        "limitations": [
            "Échantillon solo queue limité à EUW et aux joueurs suivis.",
            "Les champions peu joués sont exclus des tests principaux.",
            "Une corrélation ne démontre pas une causalité.",
            "Le nombre de champions modifiés disposant d'assez de picks est faible.",
            "Les recommandations assistent le coach et ne remplacent pas son expertise.",
        ],
    }
    (RESULTS_DIR / "statistical_analysis_results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return results


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(run(), ensure_ascii=False, indent=2, default=str))
