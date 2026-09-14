"""Pro analytics and source-separated coaching; no browser-provided SQL."""
from typing import Annotated, Literal

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


@router.get('/accounts')
def accounts(year: Annotated[int, Query(ge=2000, le=2100)],
             player: Annotated[str, Query(min_length=1, max_length=256)]):
    # Cargo text is an attribution by the wiki, not verified Riot account ownership.
    return db.query(f"""SELECT player_page, max(player_name) AS player_name,
        max(reported_soloqueue_accounts) AS reported_accounts
        FROM {TABLE} WHERE season_year=:year AND player_page=:player
        GROUP BY player_page""", {'year': year, 'player': player})


@router.get('/draft/patches')
def draft_patches():
    return db.query("""SELECT patch FROM (SELECT DISTINCT patch FROM gold.gold_pro_champion_draft_by_patch) patches
        ORDER BY CASE WHEN patch ~ '^[0-9]+([.][0-9]+)*$'
            THEN string_to_array(patch,'.')::int[] END DESC NULLS LAST, patch DESC""")


@router.get('/draft')
def draft(patch: Annotated[str, Query(min_length=1, max_length=32)]):
    return db.query("""SELECT champion_name, picks, bans, total_games, winrate,
        pickrate, banrate, presence FROM gold.gold_pro_champion_draft_by_patch
        WHERE patch=:patch ORDER BY presence DESC, picks DESC, champion_name""", {'patch': patch})


@router.get('/coaching')
def coaching(source: Literal['pro', 'soloq'],
             player: Annotated[str, Query(min_length=1, max_length=256)],
             year: Annotated[int, Query(ge=2000, le=2100)]):
    # Normalize measures, never merge the competitive and ranked populations.
    if source == 'pro':
        participations = f"""SELECT win, kills, deaths, assists, cs,
            gold, duration_min, champion FROM {TABLE}
            WHERE player_page=:player AND season_year=:year"""
    else:
        participations = """SELECT win, kills, deaths, assists, total_cs AS cs,
            gold_earned AS gold, game_duration_s/60.0 AS duration_min,
            champion_name AS champion FROM gold.fact_match_participant
            WHERE puuid=:player
            AND game_started_at >= make_date(:year,1,1)::timestamp AT TIME ZONE 'UTC'
            AND game_started_at < make_date(:year+1,1,1)::timestamp AT TIME ZONE 'UTC'"""
    return db.query(f"""WITH games AS ({participations})
        SELECT count(*) AS games, avg(win::int) AS winrate,
        count(win) AS games_with_result,
        (sum(kills+assists) FILTER (WHERE deaths IS NOT NULL))::numeric
            / nullif(sum(deaths) FILTER (WHERE kills IS NOT NULL AND assists IS NOT NULL),0) AS kda,
            count(*) FILTER (WHERE kills IS NOT NULL AND deaths IS NOT NULL AND assists IS NOT NULL) AS games_with_kda,
            avg(cs/nullif(duration_min,0)) AS cs_min,
            count(cs/nullif(duration_min,0)) AS games_with_cs_min,
            avg(gold/nullif(duration_min,0)) AS gold_min,
            count(gold/nullif(duration_min,0)) AS games_with_gold_min,
            count(distinct champion) AS champion_pool
        FROM games""", {'player': player, 'year': year})


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


def selection(params, player_a, player_b, selected_players=None):
    players = selected_players if selected_players is not None else [player_a, player_b]
    if not 2 <= len(players) <= 5 or len(set(players)) != len(players) or any(not p or len(p)>256 for p in players):
        raise HTTPException(422, "Choisis entre deux et cinq joueurs distincts.")
    return {**params, 'selected_players':players}


@router.get('/compare')
def compare(params: Annotated[dict, Depends(filters)],
            player_a: Annotated[str, Query(max_length=256)] = '',
            player_b: Annotated[str, Query(max_length=256)] = '',
            selected_players: Annotated[list[str] | None, Query(min_length=2, max_length=5)] = None):
    params = selection(params, player_a, player_b, selected_players)
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
        FROM {TABLE} WHERE {WHERE} AND player_page = ANY(CAST(:selected_players AS text[]))
        GROUP BY player_page ORDER BY player_page""", params)


@router.get('/history')
def history(params: Annotated[dict, Depends(filters)],
            player_a: Annotated[str, Query(max_length=256)] = '',
            player_b: Annotated[str, Query(max_length=256)] = '',
            selected_players: Annotated[list[str] | None, Query(min_length=2, max_length=5)] = None):
    params = selection(params, player_a, player_b, selected_players)
    return db.query(f"""WITH recent AS (
        SELECT *, row_number() OVER (PARTITION BY player_page ORDER BY game_date DESC, game_id) AS n
        FROM {TABLE} WHERE {WHERE} AND player_page = ANY(CAST(:selected_players AS text[]))
    ) SELECT player_page, player_name, game_date, tournament, competition_region, team,
        champion, role, source_patch, win, kills, deaths, assists, gold, cs,
        items, trinket, keystone_rune, primary_tree, secondary_tree, runes,
        equipment_fields_collected
      FROM recent WHERE n <= 20 ORDER BY game_date DESC, game_id, player_page""", params)
