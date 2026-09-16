"""SELECT-only test of filtering, totals and role-less bans."""
import re

from backend import pro_draft


def test_pro_draft_filters(infrastructure):
    conn=infrastructure[0]
    fixture="""WITH fixture(game_id,patch,competition_region,champion_name,role,event_type,win) AS (
        VALUES ('1','16.18','Europe','Azir','Mid','pick',true),
               ('2','16.18','Europe','Azir','Top','pick',false),
               ('3','16.18','Asia','Azir','Mid','pick',false),
               ('1','16.18','Europe','Azir',NULL,'ban',NULL),
               ('2','16.18','Europe','Zed',NULL,'ban',NULL))
        SELECT * FROM ("""
    sql=fixture+pro_draft.QUERY.replace(pro_draft.TABLE,'fixture')+') result'
    sql=re.sub(r'(?<!:):([a-z_]+)',r'%(\1)s',sql)
    def query(region='',role=''):
        with conn.cursor() as cur:
            cur.execute(sql,{'patch':'16.18','region':region,'role':role})
            return [dict(zip([c.name for c in cur.description],r)) for r in cur.fetchall()]
    all_rows=query()
    assert all_rows[0]['total_games']==3 and all_rows[0]['picks']==3
    europe=query('Europe')
    assert europe[0]['picks']==2 and europe[0]['bans']==1 and europe[0]['winrate']==0.5
    mid=query('Europe','Mid')
    assert len(mid)==1 and mid[0]['champion_name']=='Azir'
    assert mid[0]['picks']==1 and mid[0]['winrate']==1 and mid[0]['pickrate']==0.5
    assert mid[0]['bans'] is None and mid[0]['presence'] is None
    assert query('Absent')==[] and query('Europe','Jungle')==[]
