"""Read-only, same-origin API for the coaching interface. No raw SQL from clients."""

import logging
import os
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError

STATIC = Path(__file__).parent / "static"
logger = logging.getLogger(__name__)
app = FastAPI(title="MyLeague · Coaching API", docs_url=None, redoc_url=None, openapi_url=None)


@lru_cache(maxsize=1)
def get_engine():
    return create_engine(
        URL.create(
            "postgresql+psycopg2",
            username=os.getenv("DATA_ANALYST_USER", "data_analyst"),
            password=os.getenv("DATA_ANALYST_PASSWORD", ""),
            host=os.getenv("GOLD_POSTGRES_HOST", "gold-postgres"),
            port=int(os.getenv("GOLD_POSTGRES_PORT", "5432")),
            database=os.getenv("GOLD_POSTGRES_DB", "gold"),
        ),
        pool_size=3, max_overflow=2, pool_pre_ping=True,
        connect_args={"connect_timeout": 3,
                      "options": "-c default_transaction_read_only=on -c statement_timeout=8000"},
    )


def query(sql, params=None):
    with get_engine().connect() as conn:
        return [dict(row) for row in conn.execute(text(sql), params or {}).mappings()]


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'self'"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    # Do not expose connection strings, SQL parameters or player identifiers.
    logger.warning("Database unavailable at %s (%s)", request.url.path, type(exc).__name__)
    return JSONResponse(status_code=503, content={
        "detail": "Données indisponibles : vérifier PostgreSQL, les droits data_analyst et le dernier build dbt."
    })


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/healthz")
def health():
    """Container liveness only; database failures are reported by the data API."""
    return {"status": "ok"}


@app.get("/api/patches")
def patches():
    rows = query("SELECT patch FROM gold.gold_patch_summary")
    # Game patches are numeric components: 16.10 must sort after 16.9.
    def patch_key(row):
        return tuple(int(p) if p.isdigit() else -1 for p in row["patch"].split("."))
    return sorted(rows, key=patch_key, reverse=True)


# This allowlist is server-owned. No caller-controlled SQL identifiers or ORDER BY.
DATASETS = {
    "summary": ("SELECT patch, total_matches, avg_duration_min, first_game_at, last_game_at "
                "FROM gold.gold_patch_summary WHERE patch = :patch"),
    "meta": ("SELECT b.champion_name, b.picks, b.winrate, b.pickrate, b.banrate, b.presence, "
             "m.most_common_position AS role, m.kda, m.avg_cs_per_min "
             "FROM gold.gold_champion_bans_by_patch b LEFT JOIN gold.gold_champion_meta_by_patch m "
             "ON b.patch = m.patch AND b.champion_key = m.champion_key "
             "WHERE b.patch = :patch ORDER BY b.presence DESC NULLS LAST, b.picks DESC LIMIT 1000"),
    "draft": ("SELECT champion_name, role, picks, winrate, presence, pro_presence, "
              "confidence_level, priority_score, recommendation FROM gold.gold_draft_recommendations "
              "WHERE patch = :patch ORDER BY priority_score DESC, picks DESC LIMIT 1000"),
    "players": ("SELECT DISTINCT puuid, player_name FROM gold.gold_academy_player_pool_gap "
                "WHERE patch = :patch ORDER BY player_name LIMIT 1000"),
    "training": ("SELECT champion_name, role, priority_score, recommendation, mastery_level, "
                 "mastery_points, last_played_at, readiness, training_priority "
                 "FROM gold.gold_academy_player_pool_gap WHERE patch = :patch AND puuid = :player "
                 "ORDER BY training_priority DESC, priority_score DESC LIMIT 1000"),
    "items": ("SELECT item_name, times_built, winrate FROM gold.gold_champion_items_by_patch "
              "WHERE patch = :patch AND champion_name = :champion AND times_built >= 3 "
              "ORDER BY times_built DESC LIMIT 30"),
    "runes": ("SELECT keystone_name, style_name, picks, winrate FROM gold.gold_champion_keystones_by_patch "
              "WHERE patch = :patch AND champion_name = :champion ORDER BY picks DESC LIMIT 30"),
    "evolution": ("SELECT champion_name, previous_patch, picks, previous_picks, winrate, previous_winrate, "
                  "winrate_delta, pickrate_delta, trend, official_change "
                  "FROM gold.gold_champion_patch_evolution WHERE patch = :patch "
                  "ORDER BY abs(winrate_delta) DESC NULLS LAST, picks DESC LIMIT 1000"),
    "tiers": ("SELECT tier, champion_name, picks, winrate, pickrate, kda "
              "FROM gold.gold_champion_meta_by_tier WHERE patch = :patch "
              "ORDER BY tier, picks DESC LIMIT 5000"),
    "runs": ("SELECT pipeline_name, status, started_at, ended_at, records_written, error_count "
             "FROM audit.pipeline_runs ORDER BY started_at DESC LIMIT 30"),
    "alerts": ("SELECT pipeline_name, alert_type, severity, first_detected_at, last_detected_at "
               "FROM audit.pipeline_alerts WHERE resolved_at IS NULL "
               "ORDER BY last_detected_at DESC LIMIT 100"),
}


@app.get("/api/data/{dataset}")
def data(dataset: str, patch: str = Query(default="", max_length=32),
         player: str = Query(default="", max_length=256),
         champion: str = Query(default="", max_length=100)):
    if dataset not in DATASETS:
        raise HTTPException(404, "Ressource inconnue")
    if dataset not in {"runs", "alerts"} and not patch:
        raise HTTPException(422, "Un patch est requis")
    return query(DATASETS[dataset], {"patch": patch, "player": player, "champion": champion})


app.mount("/static", StaticFiles(directory=STATIC), name="static")
