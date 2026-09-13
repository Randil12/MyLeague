"""API and production React assets, served on one private origin."""
import logging
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from backend import db, queries

app = FastAPI(title="MyLeague", docs_url=None, redoc_url=None, openapi_url=None)
logger = logging.getLogger(__name__)
DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


@app.middleware("http")
async def headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(SQLAlchemyError)
async def unavailable(request, exc):
    logger.warning("Unavailable dataset %s (%s)", request.url.path, type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail":
        "Données indisponibles. Vérifie la connexion, les droits data_analyst et le dernier build dbt."})


@app.get("/healthz")
def health():
    return {"status": "ok", "database_checked": False}


@app.get("/api/patches")
def patches():
    rows = db.query(queries.PATCHES)
    return sorted(rows, key=lambda r: tuple(int(x) if x.isdigit() else -1
                  for x in r["patch"].split(".")), reverse=True)


@app.get("/api/players")
def players():
    return db.query(queries.PLAYERS)


@app.get("/api/data/{dataset}")
def dataset(dataset: str, patch: Annotated[str, Query(min_length=1, max_length=32)],
            player: Annotated[str, Query(max_length=256)] = "",
            champion: Annotated[str, Query(max_length=100)] = "",
            role: Literal["", "TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"] = "",
            minimum: Annotated[int, Query(ge=1, le=10000)] = 10):
    if dataset not in queries.DATASETS:
        raise HTTPException(404, "Analyse inconnue")
    if dataset in {"training", "player_summary", "player_matchups", "history", "progress", "durations"}:
        if not player:
            raise HTTPException(422, "Choisis un joueur")
    return db.query(queries.DATASETS[dataset], {
        "patch": patch, "player": player, "champion": champion, "role": role, "minimum": minimum,
    })


@app.get("/api/team")
def team(patch: Annotated[str, Query(min_length=1, max_length=32)],
         roster: Annotated[list[str], Query(min_length=5, max_length=5)]):
    if len(set(roster)) != 5 or any(not p or len(p) > 256 for p in roster):
        raise HTTPException(422, "Sélectionne cinq joueurs distincts")
    return db.query(queries.TEAM, {"patch": patch, "roster": roster})


@app.get("/")
def index():
    if not (DIST / "index.html").exists():
        return JSONResponse(status_code=503, content={"detail": "Construire le frontend avec npm run build."})
    return FileResponse(DIST / "index.html")


app.mount("/assets", StaticFiles(directory=DIST / "assets", check_dir=False), name="assets")
