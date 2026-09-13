"""Server-owned SQL. No SQL identifier or expression comes from the browser."""

PATCHES = "SELECT patch, total_matches, avg_duration_min, last_game_at FROM gold.gold_patch_summary"
PLAYERS = """
SELECT t.puuid,
       coalesce(n.riot_id,
                CASE WHEN t.riot_summoner_name LIKE '%#%'
                     THEN nullif(btrim(t.riot_summoner_name), t.puuid) END,
                n.display_name, nullif(nullif(btrim(t.riot_summoner_name), ''), t.puuid),
                'Pseudo indisponible') AS player_name,
       t.tier, t.tracking_source
FROM audit.riot_tracked_players t
LEFT JOIN gold.gold_player_names n ON n.puuid = t.puuid
WHERE t.is_tracked
ORDER BY (t.tracking_source = 'academy') DESC,
         t.last_seen_master_plus_at DESC NULLS LAST, t.puuid
LIMIT 500
"""
# Discard ambiguous / duplicate role assignments before matching opponents.
PAIRED = """
WITH roles AS (
 SELECT *, count(*) OVER (PARTITION BY match_id, team_id, team_position) AS role_count
 FROM gold.fact_match_participant
 WHERE patch = :patch AND team_position IN ('TOP','JUNGLE','MIDDLE','BOTTOM','UTILITY')
), paired AS (
 SELECT a.*, b.champion_name AS opponent,
        a.gold_earned - b.gold_earned AS gold_delta,
        (a.total_cs - b.total_cs) * 60.0 / nullif(a.game_duration_s, 0) AS cs_delta
 FROM roles a JOIN roles b ON a.match_id = b.match_id
   AND a.team_id <> b.team_id AND a.team_position = b.team_position
 WHERE a.role_count = 1 AND b.role_count = 1
)
"""
DATASETS = {
    "draft": """SELECT champion_name, role, picks, winrate, pickrate, banrate, presence,
        pro_presence, confidence_level, priority_score, recommendation
        FROM gold.gold_draft_recommendations WHERE patch = :patch
        ORDER BY priority_score DESC, picks DESC LIMIT 1000""",
    "flex": """WITH roles AS (
        SELECT champion_name, team_position, count(*) AS picks,
               avg(win::int) AS winrate
        FROM gold.fact_match_participant
        WHERE patch = :patch AND team_position IN ('TOP','JUNGLE','MIDDLE','BOTTOM','UTILITY')
        GROUP BY champion_name, team_position HAVING count(*) >= :minimum
    ) SELECT champion_name, count(*) AS role_count,
        string_agg(team_position || ' (' || picks || ')', ', ' ORDER BY picks DESC) AS roles,
        sum(picks) AS picks
      FROM roles GROUP BY champion_name HAVING count(*) >= 2
      ORDER BY role_count DESC, picks DESC LIMIT 200""",
    "matchups": PAIRED + """SELECT champion_name, opponent, team_position AS role,
        count(*) AS games, avg(win::int) AS winrate,
        round(avg(gold_delta),0) AS gold_delta, round(avg(cs_delta),2) AS cs_delta
        FROM paired WHERE (:champion = '' OR champion_name = :champion)
        AND (:role = '' OR team_position = :role)
        GROUP BY champion_name, opponent, team_position HAVING count(*) >= :minimum
        ORDER BY games DESC, winrate DESC LIMIT 300""",
    "compositions": """WITH teams AS (
        SELECT match_id, team_id,
          string_agg(champion_name, ' · ' ORDER BY CASE team_position
            WHEN 'TOP' THEN 1 WHEN 'JUNGLE' THEN 2 WHEN 'MIDDLE' THEN 3
            WHEN 'BOTTOM' THEN 4 ELSE 5 END) AS composition,
          bool_and(win) AS win
        FROM gold.fact_match_participant WHERE patch = :patch
          AND team_position IN ('TOP','JUNGLE','MIDDLE','BOTTOM','UTILITY')
        GROUP BY match_id, team_id
        HAVING count(*) = 5 AND count(DISTINCT team_position) = 5 AND count(DISTINCT puuid) = 5
    ) SELECT composition, count(*) AS games, avg(win::int) AS winrate
      FROM teams GROUP BY composition HAVING count(*) >= :minimum
      ORDER BY winrate DESC, games DESC LIMIT 100""",
    "training": """SELECT champion_name, role, priority_score, mastery_level, mastery_points,
        readiness, training_priority, last_played_at
        FROM gold.gold_academy_player_pool_gap WHERE patch = :patch AND puuid = :player
        ORDER BY training_priority DESC LIMIT 200""",
    "player_matchups": PAIRED + """SELECT champion_name, opponent, team_position AS role,
        count(*) AS games, avg(win::int) AS winrate,
        round(avg(gold_delta),0) AS gold_delta, round(avg(cs_delta),2) AS cs_delta
        FROM paired WHERE puuid = :player
        GROUP BY champion_name, opponent, team_position HAVING count(*) >= :minimum
        ORDER BY winrate ASC, games DESC LIMIT 100""",
    "player_summary": """SELECT count(*) AS games, avg(win::int) AS winrate,
        round(sum(kills+assists)::numeric/nullif(sum(deaths),0),2) AS kda,
        round(avg(total_cs*60.0/nullif(game_duration_s,0)),2) AS cs_min,
        round(avg(damage_to_champions*60.0/nullif(game_duration_s,0)),0) AS damage_min,
        round(avg(vision_score*60.0/nullif(game_duration_s,0)),2) AS vision_min
        FROM gold.fact_match_participant WHERE patch = :patch AND puuid = :player""",
    "history": """SELECT match_id, champion_name, team_position AS role, win, kills, deaths,
        assists, round(total_cs*60.0/nullif(game_duration_s,0),2) AS cs_min,
        round(game_duration_s/60.0,1) AS duration, game_started_at
        FROM gold.fact_match_participant WHERE patch = :patch AND puuid = :player
        ORDER BY game_started_at DESC LIMIT 50""",
    "progress": """SELECT patch, count(*) AS games, avg(win::int) AS winrate,
        round(sum(kills+assists)::numeric/nullif(sum(deaths),0),2) AS kda,
        round(avg(total_cs*60.0/nullif(game_duration_s,0)),2) AS cs_min
        FROM gold.fact_match_participant WHERE puuid = :player GROUP BY patch
        ORDER BY split_part(patch,'.',1)::int DESC, split_part(patch,'.',2)::int DESC LIMIT 24""",
    "durations": """SELECT CASE WHEN game_duration_s < 1500 THEN '< 25 min'
        WHEN game_duration_s < 2100 THEN '25–35 min' ELSE '≥ 35 min' END AS duration,
        count(*) AS games, avg(win::int) AS winrate
        FROM gold.fact_match_participant WHERE puuid = :player AND patch = :patch
        GROUP BY 1 ORDER BY 1""",
    "evolution": """SELECT champion_name, previous_patch, picks, previous_picks,
        winrate, winrate_delta, trend, official_change
        FROM gold.gold_champion_patch_evolution WHERE patch = :patch
        ORDER BY abs(winrate_delta) DESC NULLS LAST LIMIT 200""",
    "items": """SELECT item_name, times_built, winrate FROM gold.gold_champion_items_by_patch
        WHERE patch = :patch AND champion_name = :champion AND times_built >= :minimum
        ORDER BY times_built DESC LIMIT 20""",
    "runes": """SELECT keystone_name, style_name, picks, winrate
        FROM gold.gold_champion_keystones_by_patch WHERE patch = :patch AND champion_name = :champion
        ORDER BY picks DESC LIMIT 20""",
}

TEAM = """
WITH shared AS (
 SELECT match_id, team_id, patch, max(game_started_at) AS played_at,
        bool_and(win) AS win, sum(kills) AS kills, sum(deaths) AS deaths,
        sum(assists) AS assists, round(avg(game_duration_s)/60.0,1) AS duration
 FROM gold.fact_match_participant WHERE puuid = ANY(:roster)
 GROUP BY match_id, team_id, patch
 HAVING count(DISTINCT puuid) = 5 AND count(*) = 5
)
SELECT * FROM shared WHERE patch = :patch ORDER BY played_at DESC LIMIT 100
"""
