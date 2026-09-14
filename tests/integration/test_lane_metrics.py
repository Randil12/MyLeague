"""Read-only SQL fixtures exercise the actual dbt model, without mutating tables."""
import json
from pathlib import Path
from jinja2 import Environment


def evaluate(conn, *, duration=1200, timestamp=900300, missing=False, duplicate_role=False, gap=False,
             damage=15000, cs=150, full=False):
    model=Path(__file__).resolve().parents[2]/'dbt/models/gold/gold_player_lane.sql'
    sql=Environment().from_string(model.read_text(encoding='utf-8')).render(
        config=lambda **kw:'', ref=lambda _: 'fixture_facts',
        source=lambda _, table: 'fixture_matches' if table=='riot_matches' else 'fixture_timelines')
    participants=[{'puuid':'p1','participantId':1,'challenges':{'soloKills':3}},
                  {'puuid':'p2','participantId':2}]
    frames=[{'timestamp':i*60000,'events':[]} for i in range(16)]
    frames[-1]['timestamp']=timestamp
    frames[-1]['participantFrames']={'1':{'totalGold':6000,'minionsKilled':100,'jungleMinionsKilled':5,'xp':7000},
                                      '2':{'totalGold':5000,'minionsKilled':90,'jungleMinionsKilled':3,'xp':6500}}
    kill={'type':'CHAMPION_KILL','timestamp':840000,'killerId':1,'victimId':2}
    frames[-1]['events']=[kill,kill, # duplicate events count once
        {**kill,'timestamp':850000,'assistingParticipantIds':[3]},
        {**kill,'timestamp':860000,'killerId':0}, # execution excluded
        {**kill,'timestamp':900000}] # not strictly before 15 min
    if full:
        frames.extend({'timestamp':i*60000,'events':[]} for i in range(16,21))
        frames[-1]['events']=[
            {**kill,'timestamp':1100000,'killerId':2,'victimId':1},
            {**kill,'timestamp':1110000,'victimId':3}, # another opponent: exclude from pair
        ]
    if gap: frames=frames[:3]+frames[-1:]
    facts=[{'match_id':'m','puuid':'p1','champion_name':'Darius','team_id':100,'team_position':'TOP'},
           {'match_id':'m','puuid':'p2','champion_name':'Aatrox','team_id':200,'team_position':'TOP'}]
    if duplicate_role:
        participants.append({'puuid':'p3','participantId':3})
        facts.append({**facts[1],'puuid':'p3'})
    for f in facts: f.update(patch='16.18',game_started_at='2026-09-14T00:00:00Z',game_duration_s=duration,win=f['team_id']==100,
                            damage_to_champions=damage,total_cs=cs)
    fixture="""WITH fixture_matches AS (SELECT 'm'::text AS match_id, %s::jsonb AS payload),
        fixture_timelines AS (SELECT 'm'::text AS match_id, %s::jsonb AS payload),
        fixture_facts AS (SELECT * FROM jsonb_to_recordset(%s::jsonb) AS f(
            match_id text,puuid text,champion_name text,team_id int,team_position text,
            patch text,game_started_at timestamptz,game_duration_s int,win boolean,
            damage_to_champions numeric,total_cs numeric))
        SELECT * FROM ("""+sql+") result ORDER BY puuid"
    with conn.cursor() as cur:
        cur.execute(fixture,(json.dumps({'info':{'participants':participants}}),
                            json.dumps({'info':{'frames':[] if missing else frames}}),json.dumps(facts)))
        return [dict(zip([c.name for c in cur.description],r)) for r in cur.fetchall()]


def test_lane_exact_metrics(infrastructure):
    rows=evaluate(infrastructure[0])
    assert (rows[0]['gold_15'],rows[0]['gd_15'],rows[0]['csd_15'],rows[0]['xpd_15']) == (6000,1000,12,500)
    assert rows[0]['observed_at_ms']==900300
    assert rows[0]['solo_kills']==3 and rows[1]['solo_kills'] is None
    assert rows[0]['solo_kills_15']==1 and rows[1]['solo_deaths_15']==1
    assert rows[0]['solo_deaths_15']==0 and rows[1]['gd_15']==-1000


def test_rates_use_whole_match_and_do_not_require_timeline(infrastructure):
    conn=infrastructure[0]
    row=evaluate(conn,missing=True)[0]
    assert row['damage_min']==750 and row['cs_min']==7.5
    for duration in [None,0,-1]:
        row=evaluate(conn,duration=duration)[0]
        assert row['damage_min'] is None and row['cs_min'] is None
    row=evaluate(conn,damage=None,cs=None)[0]
    assert row['damage_min'] is None and row['cs_min'] is None
    row=evaluate(conn,damage=0,cs=0)[0]
    assert row['damage_min']==0 and row['cs_min']==0


def test_lane_missing_short_and_ambiguous(infrastructure):
    conn=infrastructure[0]
    for kwargs in [{'missing':True},{'duration':899}]:
        row=evaluate(conn,**kwargs)[0]
        assert row['gold_15'] is None and row['solo_kills_15'] is None
    assert evaluate(conn,timestamp=906000)[0]['gold_15'] is None
    assert evaluate(conn,duplicate_role=True)[0]['gd_15'] is None
    assert evaluate(conn,gap=True)[0]['solo_kills_15'] is None


def test_directional_solo_kills_require_full_timeline(infrastructure):
    conn=infrastructure[0]
    a,b=evaluate(conn,full=True)
    assert (a['solo_kills_vs_opponent'],a['solo_deaths_vs_opponent'])==(2,1)
    assert (b['solo_kills_vs_opponent'],b['solo_deaths_vs_opponent'])==(1,2)
    for options in ({},{'missing':True},{'full':True,'gap':True},{'full':True,'duplicate_role':True}):
        a=evaluate(conn,**options)[0]
        assert a['solo_kills_vs_opponent'] is None
        assert a['solo_deaths_vs_opponent'] is None
