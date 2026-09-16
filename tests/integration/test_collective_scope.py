from backend.queries import TEAM


def test_shared_games_require_every_selected_player_on_same_team(infrastructure):
    fixture = """WITH facts AS (
      SELECT match_id,puuid,team_id,patch,now() AS game_started_at,
        true AS win,1 AS kills,2 AS deaths,3 AS assists,1800 AS game_duration_s
      FROM (VALUES
        ('together','a',100,'16.17'),('together','b',100,'16.17'),
        ('opponents','a',100,'16.18'),('opponents','b',200,'16.18'),
        ('alone','a',100,'16.18'),
        ('three','a',100,'16.18'),('three','b',100,'16.18'),('three','c',100,'16.18')
      ) v(match_id,puuid,team_id,patch))
    """
    sql = TEAM.replace('gold.fact_match_participant', 'facts')
    sql = sql.replace(':roster', '%(roster)s').replace(':patch', '%(patch)s')
    # Nest the production WITH under the fixture without changing its semantics.
    with infrastructure[0].cursor() as cur:
        for roster, patch, expected in [
            (['a', 'b'], '', {'together', 'three'}),
            (['a', 'b'], '16.18', {'three'}),
            (['a', 'b', 'c'], '', {'three'}),
            (['a', 'b', 'missing'], '', set()),
        ]:
            cur.execute(fixture + 'SELECT * FROM (' + sql + ') result', {'roster': roster, 'patch': patch})
            rows = [dict(zip([c.name for c in cur.description], r)) for r in cur.fetchall()]
            assert {r['match_id'] for r in rows} == expected
            assert all(r['kills'] == len(roster) for r in rows)
