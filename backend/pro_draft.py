"""Regional and role-aware competitive draft statistics."""
TABLE = 'gold.gold_pro_draft_events'
QUERY = f"""WITH scoped AS (
    SELECT * FROM {TABLE} WHERE patch=:patch
      AND (:region='' OR competition_region=:region)
), total AS (SELECT count(DISTINCT game_id) AS total_games FROM scoped),
stats AS (
    SELECT champion_name,
        count(*) FILTER(WHERE event_type='pick' AND (:role='' OR role=:role)) AS picks,
        count(*) FILTER(WHERE event_type='ban') AS all_bans,
        avg(win::int) FILTER(WHERE event_type='pick' AND (:role='' OR role=:role)) AS winrate
    FROM scoped GROUP BY champion_name
)
SELECT champion_name,picks,CASE WHEN :role='' THEN all_bans END AS bans,
    total_games,winrate,picks::numeric/nullif(total_games,0) AS pickrate,
    CASE WHEN :role='' THEN all_bans::numeric/nullif(total_games,0) END AS banrate,
    CASE WHEN :role='' THEN (picks+all_bans)::numeric/nullif(total_games,0) END AS presence
FROM stats CROSS JOIN total
WHERE picks>0 OR (:role='' AND all_bans>0)
ORDER BY CASE WHEN :role='' THEN picks+all_bans ELSE picks END DESC,champion_name"""
