"""Competitive comparisons only: no join to solo queue, no browser-provided SQL."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from backend import db

router = APIRouter(prefix="/api/pro")
TABLE = "gold.gold_pro_player_games"
WHERE = """season_year=:year
    AND (:region='' OR competition_region=:region)
    AND (:tournament='' OR tournament_page=:tournament)
    AND (:role='' OR role=:role)
    AND (:champion='' OR champion=:champion)
    AND (:patch='' OR source_patch=:patch)"""


def filters(
    year: Annotated[int, Query(ge=2000, le=2100)],
    region: Annotated[str, Query(max_length=100)] = "",
    tournament: Annotated[str, Query(max_length=512)] = "",
    role: Annotated[str, Query(max_length=40)] = "",
    champion: Annotated[str, Query(max_length=100)] = "",
    patch: Annotated[str, Query(max_length=32)] = "",
):
    return dict(year=year, region=region, tournament=tournament, role=role, champion=champion, patch=patch)


@router.get('/years')
def years():
    return db.query(f"SELECT DISTINCT season_year AS year FROM {TABLE} ORDER BY year DESC")


@router.get('/options')
def options(year: Annotated[int, Query(ge=2000, le=2100)]):
    # Exact observed combinations preserve tournament/region relationships.
    return db.query(f"""SELECT DISTINCT competition_region, tournament_page, tournament,
        role, champion, source_patch FROM {TABLE} WHERE season_year=:year
        ORDER BY competition_region, tournament_page, role, champion, source_patch""", {'year':year})


@router.get('/players')
def players(params: Annotated[dict, Depends(filters)]):
    return db.query(f"""SELECT player_page, max(player_name) AS player_name, count(*) AS games
        FROM {TABLE} WHERE {WHERE} GROUP BY player_page ORDER BY games DESC, player_page""", params)


def selection(params, player_a, player_b):
    if player_a == player_b:
        raise HTTPException(422, "Choisis deux joueurs distincts.")
    return {**params, 'player_a':player_a, 'player_b':player_b}


@router.get('/compare')
def compare(params: Annotated[dict, Depends(filters)],
            player_a: Annotated[str, Query(min_length=1, max_length=256)],
            player_b: Annotated[str, Query(min_length=1, max_length=256)]):
    params = selection(params, player_a, player_b)
    return db.query(f"""SELECT player_page, max(player_name) AS player_name,
        count(*) AS games, count(win) AS games_with_result,
        count(*) FILTER (WHERE win) AS wins, avg(win::int) AS winrate,
        count(*) FILTER (WHERE kills IS NOT NULL AND deaths IS NOT NULL AND assists IS NOT NULL) AS games_with_kda,
        sum(kills+assists) FILTER (WHERE deaths IS NOT NULL)
          / nullif(sum(deaths) FILTER (WHERE kills IS NOT NULL AND assists IS NOT NULL),0) AS kda,
        avg(kills) AS avg_kills, avg(deaths) AS avg_deaths, avg(assists) AS avg_assists,
        count(kills) AS games_with_kills, count(deaths) AS games_with_deaths,
        count(assists) AS games_with_assists,
        avg(cs) AS avg_cs, count(cs) AS games_with_cs,
        avg(gold) AS avg_gold, count(gold) AS games_with_gold,
        avg(cs/nullif(duration_min,0)) AS cs_min,
        count(cs/nullif(duration_min,0)) AS games_with_cs_min,
        avg(gold/nullif(duration_min,0)) AS gold_min,
        count(gold/nullif(duration_min,0)) AS games_with_gold_min,
        avg(damage_to_champions) AS avg_damage, count(damage_to_champions) AS games_with_damage,
        avg(vision_score) AS avg_vision, count(vision_score) AS games_with_vision,
        count(distinct champion) AS champion_pool, max(game_date) AS last_game_at
        FROM {TABLE} WHERE {WHERE} AND player_page IN (:player_a,:player_b)
        GROUP BY player_page ORDER BY player_page""", params)


@router.get('/history')
def history(params: Annotated[dict, Depends(filters)],
            player_a: Annotated[str, Query(min_length=1, max_length=256)],
            player_b: Annotated[str, Query(min_length=1, max_length=256)]):
    params = selection(params, player_a, player_b)
    return db.query(f"""WITH recent AS (
        SELECT *, row_number() OVER (PARTITION BY player_page ORDER BY game_date DESC, game_id) AS n
        FROM {TABLE} WHERE {WHERE} AND player_page IN (:player_a,:player_b)
    ) SELECT player_page, player_name, game_date, tournament, competition_region, team,
        champion, role, source_patch, win, kills, deaths, assists, gold, cs,
        items, trinket, keystone_rune, primary_tree, secondary_tree, runes
      FROM recent WHERE n <= 20 ORDER BY game_date DESC, game_id, player_page""", params)
