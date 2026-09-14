"""Read-only SQL fixture for top-five champions in the current ladder."""
from backend import queries


def test_leaderboard_top_five_and_missing_history(infrastructure):
    sql=queries.LEADERBOARD.replace('audit.riot_tracked_players','tracked').replace('gold.gold_player_names','names').replace('gold.fact_match_participant','facts')
    prefix="""WITH tracked AS (
      SELECT puuid,puuid||'#EUW' AS riot_summoner_name,'CHALLENGER' AS tier,
        lp AS league_points,100 AS wins,50 AS losses,now() AS last_seen_master_plus_at,
        'euw1' AS region,true AS is_currently_master_plus,'RANKED_SOLO_5x5' AS queue_type
      FROM (VALUES ('p1',1000),('p2',900)) t(puuid,lp)
    ), names AS (SELECT ''::text AS puuid,NULL::text AS riot_id,NULL::text AS display_name WHERE false),
    facts AS (
      SELECT 'p1'::text AS puuid,'Champion'||i AS champion_name,
        i||'-'||j AS match_id,now() AS game_started_at
      FROM generate_series(1,6) i CROSS JOIN LATERAL generate_series(1,i) j
      UNION ALL SELECT 'p1','OldChampion','old',date_trunc('year',now())-interval '1 day'
    ) SELECT * FROM ("""
    with infrastructure[0].cursor() as cur:
        cur.execute(prefix+sql+') result')
        rows=[dict(zip([c.name for c in cur.description],r)) for r in cur.fetchall()]
    assert len(rows)==2 and 'puuid' not in rows[0]
    assert rows[0]['champion_sample_games']==21
    assert [rows[0][f'champion_{i}'] for i in range(1,6)]==['Champion6','Champion5','Champion4','Champion3','Champion2']
    assert [rows[0][f'champion_{i}_games'] for i in range(1,6)]==[6,5,4,3,2]
    assert rows[1]['champion_sample_games']==0 and rows[1]['champion_1'] is None
