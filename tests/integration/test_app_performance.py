"""Exercise the actual PostgreSQL queries behind performance pages."""
from fastapi.testclient import TestClient

from backend import db
from backend.main import app


def test_performance_pages_use_real_warehouse(infrastructure):
    conn, _ = infrastructure
    with conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO audit.riot_tracked_players
            (puuid,region,riot_summoner_name,tier,league_points,wins,losses,queue_type,
             first_seen_master_plus_at,last_seen_master_plus_at,is_currently_master_plus)
            SELECT 'ci-challenger-'||i,'euw1','Challenger'||i||'#EUW','CHALLENGER',2000-i,
                   100,50,'RANKED_SOLO_5x5',now(),now(),true FROM generate_series(1,300) i
            ON CONFLICT(puuid) DO NOTHING""")
    db.engine.cache_clear()
    try:
        with TestClient(app) as client:
            ladder=client.get('/api/leaderboard')
            assert ladder.status_code == 200 and len(ladder.json()) == 300
            assert ladder.json()[0]['player_name'] == 'Challenger1#EUW'
            assert 'puuid' not in ladder.json()[0]
            assert client.get('/api/champions').status_code == 200
            players=client.get('/api/players')
            assert players.status_code == 200
            assert any(p['puuid']=='ci-p1' and p['collected_games']==2 for p in players.json())
            training=client.get('/api/data/training',params={'patch':'26.18','player':'ci-p1'})
            assert training.status_code == 200 and training.json()[0]['games']==2
            team=client.get('/api/team/summary',params={'patch':'26.18','roster':[f'ci-p{i}' for i in range(1,6)]})
            assert team.status_code == 200 and len(team.json()) == 5
            assert all(p['games']==2 for p in team.json())
    finally:
        db.engine().dispose()
        db.engine.cache_clear()
