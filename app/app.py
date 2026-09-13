"""MyLeague — Application web d'analyse de la méta (Nexus Esport Academy).

Se connecte à l'entrepôt avec le rôle data_analyst (lecture seule sur
gold/reference/audit) : l'application ne peut ni écrire ni voir les zones brutes.
"""

from __future__ import annotations

import os

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

st.set_page_config(page_title="MyLeague — Méta LoL", page_icon="🏆", layout="wide")


# ---------------------------------------------------------------------------
# Connexion (rôle lecture seule)
# ---------------------------------------------------------------------------
@st.cache_resource
def get_engine():
    user = os.getenv("DATA_ANALYST_USER", "data_analyst")
    password = os.getenv("DATA_ANALYST_PASSWORD", "")
    host = os.getenv("GOLD_POSTGRES_HOST", "gold-postgres")
    port = os.getenv("GOLD_POSTGRES_PORT", "5432")
    db = os.getenv("GOLD_POSTGRES_DB", "gold")
    return create_engine(
        URL.create(
            "postgresql+psycopg2",
            username=user,
            password=password,
            host=host,
            port=int(port),
            database=db,
        ),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3},
    )


@st.cache_data(ttl=300)
def query(sql: str, params: dict | None = None) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


def safe_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    try:
        return query(sql, params)
    except Exception as exc:  # noqa: BLE001 - message d'accueil si les tables n'existent pas encore
        st.warning(
            "Données indisponibles. Vérifie que les DAGs `datadragon_ingestion`, "
            "`riot_euw_ingestion` puis `dbt_transform` ont tourné au moins une fois."
        )
        with st.expander("Détail technique"):
            st.code(str(exc))
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Barre latérale
# ---------------------------------------------------------------------------
st.sidebar.title("🏆 MyLeague")
st.sidebar.caption("Plateforme d'analyse de la méta — Nexus Esport Academy")

page = st.sidebar.radio(
    "Navigation",
    [
        "Tier list",
        "Préparation de draft",
        "Évolution des patchs",
        "Plan d'entraînement",
        "Builds par champion",
        "Méta par niveau de jeu",
        "Supervision",
    ],
)

patches = safe_query("SELECT patch FROM gold.gold_patch_summary ORDER BY patch DESC")
if patches.empty:
    st.stop()

patch = st.sidebar.selectbox("Patch", patches["patch"].tolist())
st.sidebar.divider()
st.sidebar.caption("Connexion : rôle `data_analyst` (lecture seule)")


# ---------------------------------------------------------------------------
# Page : Tier list
# ---------------------------------------------------------------------------
if page == "Tier list":
    st.title(f"Tier list — patch {patch}")

    resume = safe_query(
        "SELECT total_matches, avg_duration_min FROM gold.gold_patch_summary WHERE patch = :p",
        {"p": patch},
    )
    if not resume.empty:
        c1, c2 = st.columns(2)
        c1.metric("Matchs analysés", int(resume.iloc[0]["total_matches"]))
        c2.metric("Durée moyenne (min)", float(resume.iloc[0]["avg_duration_min"]))

    min_picks = st.slider("Picks minimum", 1, 100, 10)

    df = safe_query(
        """
        SELECT
            b.champion_name AS "Champion",
            b.picks AS "Picks",
            round(coalesce(b.winrate, 0) * 100, 1) AS "Winrate %",
            round(b.pickrate * 100, 1) AS "Pickrate %",
            round(b.banrate * 100, 1) AS "Banrate %",
            round(b.presence * 100, 1) AS "Presence %"
        FROM gold.gold_champion_bans_by_patch b
        WHERE b.patch = :p AND b.picks >= :mp
        ORDER BY b.presence DESC
        """,
        {"p": patch, "mp": min_picks},
    )

    if not df.empty:
        left, right = st.columns([3, 2])
        left.dataframe(df, use_container_width=True, hide_index=True, height=520)
        top = df.head(15).sort_values("Presence %")
        fig = px.bar(
            top, x="Presence %", y="Champion", orientation="h",
            title="Top 15 priorité de draft (presence pick + ban)",
        )
        right.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Page : Préparation de draft
# ---------------------------------------------------------------------------
elif page == "Préparation de draft":
    st.title(f"Préparation de draft — patch {patch}")
    st.caption(
        "Le score combine présence ladder (40 %), performance (20 %), présence "
        "professionnelle (20 %) et robustesse de l'échantillon (20 %)."
    )

    draft = safe_query(
        """
        SELECT champion_name, role, picks, total_matches, winrate, pickrate,
               banrate, presence, pro_presence, confidence_level,
               priority_score, recommendation
        FROM gold.gold_draft_recommendations
        WHERE patch = :p
        ORDER BY priority_score DESC, picks DESC
        """,
        {"p": patch},
    )
    if not draft.empty:
        available_roles = ["Tous"] + sorted(draft["role"].dropna().unique().tolist())
        c1, c2 = st.columns(2)
        role = c1.selectbox("Rôle", available_roles)
        min_confidence = c2.selectbox(
            "Confiance minimale",
            ["faible", "moyenne", "élevée"],
            index=1,
        )
        confidence_rank = {"faible": 0, "moyenne": 1, "élevée": 2}
        filtered = draft[
            draft["confidence_level"].map(confidence_rank).fillna(0)
            >= confidence_rank[min_confidence]
        ].copy()
        if role != "Tous":
            filtered = filtered[filtered["role"] == role]

        unavailable = st.multiselect(
            "Champions déjà pick/ban ou indisponibles",
            filtered["champion_name"].tolist(),
        )
        filtered = filtered[~filtered["champion_name"].isin(unavailable)]

        if filtered.empty:
            st.info("Aucune recommandation ne correspond aux filtres sélectionnés.")
        else:
            top = filtered.head(10).copy()
            top["Winrate %"] = (top["winrate"] * 100).round(1)
            top["Présence %"] = (top["presence"] * 100).round(1)
            top["Présence pro %"] = (top["pro_presence"] * 100).round(1)
            st.dataframe(
                top[
                    [
                        "champion_name", "role", "priority_score", "recommendation",
                        "picks", "Winrate %", "Présence %", "Présence pro %",
                        "confidence_level",
                    ]
                ].rename(
                    columns={
                        "champion_name": "Champion",
                        "role": "Rôle",
                        "priority_score": "Score",
                        "recommendation": "Recommandation",
                        "picks": "Échantillon",
                        "confidence_level": "Confiance",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )
            best = top.iloc[0]
            st.success(
                f"Priorité actuelle : {best['champion_name']} ({best['role']}) — "
                f"score {best['priority_score']}/100, {best['picks']} parties, "
                f"confiance {best['confidence_level']}."
            )


# ---------------------------------------------------------------------------
# Page : Évolution des patchs
# ---------------------------------------------------------------------------
elif page == "Évolution des patchs":
    st.title(f"Évolution de la méta — patch {patch}")
    st.caption("Comparaison avec le patch précédent disponible dans l'entrepôt.")

    evolution = safe_query(
        """
        SELECT champion_name, previous_patch, picks, previous_picks,
               round(winrate * 100, 1) AS winrate_pct,
               round(previous_winrate * 100, 1) AS previous_winrate_pct,
               round(winrate_delta * 100, 2) AS winrate_delta_points,
               round(pickrate_delta * 100, 2) AS pickrate_delta_points,
               trend, official_change, source_url
        FROM gold.gold_champion_patch_evolution
        WHERE patch = :p
        ORDER BY abs(winrate_delta) DESC NULLS LAST, picks DESC
        """,
        {"p": patch},
    )
    if not evolution.empty:
        trend = st.multiselect(
            "Tendances",
            evolution["trend"].dropna().unique().tolist(),
            default=evolution["trend"].dropna().unique().tolist(),
        )
        shown = evolution[evolution["trend"].isin(trend)].copy()
        st.dataframe(
            shown.rename(
                columns={
                    "champion_name": "Champion",
                    "previous_patch": "Patch précédent",
                    "picks": "Picks",
                    "previous_picks": "Picks précédents",
                    "winrate_pct": "Winrate %",
                    "previous_winrate_pct": "Winrate précédent %",
                    "winrate_delta_points": "Δ winrate (points)",
                    "pickrate_delta_points": "Δ pickrate (points)",
                    "trend": "Tendance",
                    "official_change": "Changement officiel",
                    "source_url": "Source",
                }
            ),
            use_container_width=True,
            hide_index=True,
            height=570,
        )


# ---------------------------------------------------------------------------
# Page : Plan d'entraînement et coaching
# ---------------------------------------------------------------------------
elif page == "Plan d'entraînement":
    st.title(f"Plan d'entraînement — patch {patch}")
    players = safe_query(
        """
        SELECT DISTINCT puuid, player_name
        FROM gold.gold_academy_player_pool_gap
        WHERE patch = :p
        ORDER BY player_name
        """,
        {"p": patch},
    )
    if players.empty:
        st.info(
            "Aucun joueur academy exploitable. Enregistre un joueur avec "
            "`python -m jobs.riot.academy register --riot-id 'GameName#TAG'`, "
            "puis exécute `riot_academy_tracking` et `dbt_transform`."
        )
    else:
        player_labels = dict(zip(players["player_name"], players["puuid"], strict=False))
        player_name = st.selectbox("Joueur", list(player_labels))
        pool = safe_query(
            """
            SELECT champion_name, role, priority_score, recommendation,
                   mastery_level, mastery_points, last_played_at,
                   readiness, training_priority
            FROM gold.gold_academy_player_pool_gap
            WHERE patch = :p AND puuid = :puuid
            ORDER BY training_priority DESC, priority_score DESC
            """,
            {"p": patch, "puuid": player_labels[player_name]},
        )
        if not pool.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric("Champions évalués", len(pool))
            c2.metric("Prêts", int((pool["readiness"] == "prêt").sum()))
            c3.metric("À acquérir", int((pool["readiness"] == "à acquérir").sum()))

            role_filter = st.selectbox(
                "Rôle à travailler",
                ["Tous"] + sorted(pool["role"].dropna().unique().tolist()),
            )
            if role_filter != "Tous":
                pool = pool[pool["role"] == role_filter]

            st.dataframe(
                pool.head(20).rename(
                    columns={
                        "champion_name": "Champion",
                        "role": "Rôle",
                        "priority_score": "Priorité méta",
                        "recommendation": "Usage draft",
                        "mastery_level": "Niveau maîtrise",
                        "mastery_points": "Points maîtrise",
                        "last_played_at": "Dernière partie",
                        "readiness": "État",
                        "training_priority": "Priorité entraînement",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )
            priorities = pool[pool["readiness"] != "prêt"].head(3)
            if not priorities.empty:
                names = ", ".join(priorities["champion_name"].tolist())
                st.warning(f"Priorités de la prochaine séance : {names}.")


# ---------------------------------------------------------------------------
# Page : Builds par champion
# ---------------------------------------------------------------------------
elif page == "Builds par champion":
    st.title(f"Builds gagnants — patch {patch}")

    champions = safe_query(
        "SELECT DISTINCT champion_name FROM gold.gold_champion_meta_by_patch "
        "WHERE patch = :p ORDER BY champion_name",
        {"p": patch},
    )
    if champions.empty:
        st.stop()

    champion = st.selectbox("Champion", champions["champion_name"].tolist())

    stats = safe_query(
        """
        SELECT picks, round(winrate * 100, 1) AS winrate_pct, kda,
               avg_cs_per_min, most_common_position
        FROM gold.gold_champion_meta_by_patch
        WHERE patch = :p AND champion_name = :c
        """,
        {"p": patch, "c": champion},
    )
    if not stats.empty:
        s = stats.iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Picks", int(s["picks"]))
        c2.metric("Winrate", f"{s['winrate_pct']} %")
        c3.metric("KDA", float(s["kda"]) if s["kda"] is not None else 0.0)
        c4.metric("Rôle principal", s["most_common_position"] or "—")

    col_items, col_runes = st.columns(2)

    with col_items:
        st.subheader("Objets")
        items = safe_query(
            """
            SELECT item_name AS "Objet", times_built AS "Builds",
                   round(winrate * 100, 1) AS "Winrate %"
            FROM gold.gold_champion_items_by_patch
            WHERE patch = :p AND champion_name = :c AND times_built >= 3
            ORDER BY winrate DESC, times_built DESC
            LIMIT 20
            """,
            {"p": patch, "c": champion},
        )
        st.dataframe(items, use_container_width=True, hide_index=True)

    with col_runes:
        st.subheader("Runes keystone")
        runes = safe_query(
            """
            SELECT keystone_name AS "Keystone", style_name AS "Branche",
                   picks AS "Picks", round(winrate * 100, 1) AS "Winrate %"
            FROM gold.gold_champion_keystones_by_patch
            WHERE patch = :p AND champion_name = :c
            ORDER BY picks DESC
            """,
            {"p": patch, "c": champion},
        )
        st.dataframe(runes, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Page : Méta par niveau de jeu
# ---------------------------------------------------------------------------
elif page == "Méta par niveau de jeu":
    st.title(f"Méta par niveau de jeu — patch {patch}")
    st.caption(
        "Tier du joueur source du match. Pour élargir au-delà de Master+, "
        "configurer RIOT_EUW_EXTRA_TIERS (ex : DIAMOND:I:1,EMERALD:I:1)."
    )

    df = safe_query(
        """
        SELECT tier AS "Tier", champion_name AS "Champion", picks AS "Picks",
               round(winrate * 100, 1) AS "Winrate %",
               round(pickrate * 100, 1) AS "Pickrate %", kda AS "KDA"
        FROM gold.gold_champion_meta_by_tier
        WHERE patch = :p AND picks >= 5
        ORDER BY tier, winrate DESC
        """,
        {"p": patch},
    )
    if not df.empty:
        tiers = df["Tier"].unique().tolist()
        tier = st.selectbox("Tier", tiers)
        st.dataframe(
            df[df["Tier"] == tier], use_container_width=True, hide_index=True, height=560
        )


# ---------------------------------------------------------------------------
# Page : Supervision
# ---------------------------------------------------------------------------
elif page == "Supervision":
    st.title("Supervision des pipelines")

    counts = safe_query(
        """
        SELECT
            (SELECT count(*) FROM audit.riot_match_ingestion WHERE status = 'success') AS bronze_ok,
            (SELECT count(*) FROM audit.riot_match_ingestion WHERE status IN ('failed', 'pending')) AS bronze_ko,
            (SELECT count(*) FROM audit.riot_tracked_players WHERE is_tracked) AS joueurs
        """
    )
    if not counts.empty:
        c = counts.iloc[0]
        c1, c2, c3 = st.columns(3)
        c1.metric("Matchs ingérés", int(c["bronze_ok"]))
        c2.metric("En échec / attente", int(c["bronze_ko"]))
        c3.metric("Joueurs suivis", int(c["joueurs"]))

    st.subheader("Derniers runs")
    runs = safe_query(
        """
        SELECT run_id AS "Run", pipeline_name AS "Pipeline", status AS "Statut",
               started_at AS "Début", ended_at AS "Fin",
               records_written AS "Écrits", error_count AS "Erreurs"
        FROM audit.pipeline_runs
        ORDER BY started_at DESC
        LIMIT 20
        """
    )
    st.dataframe(runs, use_container_width=True, hide_index=True)

    st.subheader("Alertes actives")
    alerts = safe_query(
        """
        SELECT pipeline_name AS "Pipeline", alert_type AS "Type",
               severity AS "Sévérité", message AS "Message",
               first_detected_at AS "Première détection",
               last_detected_at AS "Dernière détection",
               notification_sent AS "Notification envoyée"
        FROM audit.pipeline_alerts
        WHERE resolved_at IS NULL
        ORDER BY CASE severity WHEN 'critical' THEN 0 ELSE 1 END,
                 last_detected_at DESC
        """
    )
    if alerts.empty:
        st.success("Aucune alerte pipeline active.")
    else:
        st.dataframe(alerts, use_container_width=True, hide_index=True)
