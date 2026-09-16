"""All-patch aggregates must not silently become latest-patch or last-200 aggregates."""
from backend.queries import DATASETS


def test_player_summary_and_pool_use_complete_scope(infrastructure):
    fixture="""WITH facts AS (
        SELECT 'm'||n AS match_id,'p'::text AS puuid,'Azir'::text AS champion_name,
          'MIDDLE'::text AS team_position,n<=100 AS win,1 AS kills,1 AS deaths,
          2 AS assists,150 AS total_cs,1800 AS game_duration_s,
          10000 AS damage_to_champions,10 AS vision_score,
          CASE WHEN n<=7 THEN '16.18' ELSE '16.17' END AS patch,
          now() AS game_started_at FROM generate_series(1,216) n
    ), lane AS (
        SELECT match_id,puuid,CASE WHEN match_id='m1' THEN 100 END AS gd_15,
            NULL::numeric AS xpd_15 FROM facts
    ) """
    with infrastructure[0].cursor() as cur:
        for patch,expected in [('',216),('16.18',7)]:
            for dataset in ['player_summary','training']:
                sql=DATASETS[dataset].replace('gold.fact_match_participant','facts').replace('gold.gold_player_lane','lane')
                sql=sql.replace(':patch','%(patch)s').replace(':player','%(player)s')
                cur.execute(fixture+sql,{'patch':patch,'player':'p'})
                rows=[dict(zip([c.name for c in cur.description],r)) for r in cur.fetchall()]
                assert sum(r['games'] for r in rows)==expected
                if dataset=='training':
                    assert rows[0]['gd_15']==100 and rows[0]['games_with_gd_15']==1
                    assert rows[0]['xpd_15'] is None and rows[0]['games_with_xpd_15']==0
