"""Real PostgreSQL persistence; only runs on the isolated CI infrastructure."""
import subprocess
from pathlib import Path

import pytest

from jobs.riot.training import init_training, request


def test_goal_measurements_select_only(infrastructure):
    class FixtureCursor:
        def __init__(self, cur):
            self.cur=cur

        def execute(self, sql, params):
            if 'raw.riot_live_roster' in sql:
                self.cur.execute('SELECT 1')
                return
            fixtures="""WITH goals AS (
                SELECT 1::bigint id,'p'::text puuid,'Lane'::text title,'gd_15'::text metric,
                    0::float8 threshold,''::text champion,''::text role,
                    '2026-01-01'::date starts_on,'2026-01-07'::date ends_on,'active'::text status
            ), sessions AS (
                SELECT 1::bigint id,1::bigint goal_id,now()::date played_on,''::text notes WHERE false
            ), lane AS (
                SELECT 'p'::text puuid,'Azir'::text champion_name,'MIDDLE'::text role,
                    '2026-01-02'::timestamptz game_started_at,v::numeric gd_15,
                    NULL::numeric xpd_15,NULL::numeric cs_min,NULL::numeric damage_min,
                    NULL::numeric solo_deaths_15 FROM (VALUES (100),(-100),(0),(NULL)) x(v)
            ) """
            self.cur.execute(fixtures+sql.replace('app.training_goals','goals')
                             .replace('app.training_sessions','sessions')
                             .replace('gold.gold_player_lane','lane'),params)

        def __getattr__(self, name):
            return getattr(self.cur,name)

    with infrastructure[0].cursor() as cur:
        rows=request(FixtureCursor(cur),{'action':'list','player':'p'})
    assert len(rows)==1
    assert (rows[0]['games'],rows[0]['evaluated'],rows[0]['success'],rows[0]['mean'])==(4,3,2,0)


def test_goals_sessions_and_player_isolation(infrastructure, tmp_path):
    conn=infrastructure[0]
    root=Path(__file__).resolve().parents[2]
    subprocess.run(['dbt','run','--select','gold_player_lane','--project-dir',str(root/'dbt'),
                    '--profiles-dir',str(root/'dbt/profiles'),'--target-path',str(tmp_path/'target'),
                    '--log-path',str(tmp_path/'logs')],check=True,timeout=180)
    with conn, conn.cursor() as cur:
        init_training(cur)
        cur.execute("INSERT INTO raw.riot_live_roster(puuid,riot_id) VALUES ('ci-plan','Plan#EUW') ON CONFLICT DO NOTHING")
        body=dict(action='create',player='ci-plan',title='Lane plan',metric='gd_15',threshold=0,
                  champion='',role='',starts_on='2026-01-01',ends_on='2026-01-07')
        goal_id=request(cur,body)['id']
    # Separate transaction: persisted, not in-memory session state.
    with conn,conn.cursor() as cur:
        listed=request(cur,{'action':'list','player':'ci-plan'})
        row=next(r for r in listed if r['id']==goal_id)
        assert row['evaluated']==0 and row['mean'] is None and row['success']==0
        request(cur,dict(action='session',player='ci-plan',id=goal_id,played_on='2026-01-02',notes='Review completed'))
        request(cur,dict(action='status',player='ci-plan',id=goal_id,status='completed'))
        row=next(r for r in request(cur,{'action':'list','player':'ci-plan'}) if r['id']==goal_id)
        assert row['status']=='completed' and row['sessions'][0]['notes']=='Review completed'
        with pytest.raises(ValueError):
            request(cur,dict(action='status',player='not-in-roster',id=goal_id,status='archived'))
