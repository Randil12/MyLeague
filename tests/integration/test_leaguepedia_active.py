"""Real MinIO -> raw -> dbt analytics; only external Cargo responses are simulated."""
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from backend import db
from backend.main import app
from jobs.leaguepedia import yearly

ROOT = Path(__file__).resolve().parents[2]


def test_annual_player_pipeline(infrastructure, monkeypatch, tmp_path):
    conn, s3 = infrastructure
    with conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO raw.leaguepedia_players(overview_page,payload)
            VALUES ('CI Pro','{"ID":"CI Pro","SoloqueueIds":"Example#EUW"}')
            ON CONFLICT(overview_page) DO UPDATE SET payload=EXCLUDED.payload""")
        cur.execute("""INSERT INTO raw.leaguepedia_tournaments(overview_page,payload)
            VALUES ('CI/2026','{"Name":"CI Cup","Region":"Europe"}')
            ON CONFLICT(overview_page) DO UPDATE SET payload=EXCLUDED.payload""")
    now = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(yearly.ingest, "utc_now", lambda: now)
    monkeypatch.setattr(yearly.ingest, "get_client", lambda: object())

    def games(client, lower, **kwargs):
        day = lower[:10]
        return [{"GameId": f"CI-LP-{day}", "Patch": "26.1", "DateTime_UTC": lower,
                 "Tournament": "CI Cup", "OverviewPage": "CI/2026", "Team1": "A",
                 "Team2": "B", "Gamelength_Number":"30", "Team1Picks":"Azir", "Team2Picks":"Ornn",
                 "WinTeam": "A" if day.endswith("01") else "B"}]

    def players(client, lower, **kwargs):
        return [{"GameId": f"CI-LP-{lower[:10]}", "Link": "CI Pro", "Team": "A",
                 "Role": "Mid", "Champion": "Azir", "DateTime_UTC": lower,
                 "Kills": "4", "Deaths": "2", "Assists": "6", "CS": "200", "Gold": "12000",
                 "Items":"Item A;Item B", "Trinket":"", "KeystoneRune":"Conqueror",
                 "PrimaryTree":"Precision", "SecondaryTree":"Resolve", "Runes":"Conqueror", "VisionScore":"20",
                 "DamageToChampions":"18000"},
                {"GameId": f"CI-LP-{lower[:10]}", "Link": "CI Missing Stats", "Team": "Unknown",
                 "Role": "Top", "Champion": "Ornn", "DateTime_UTC": lower,
                 "Kills": "", "Deaths": "N/A"}]

    monkeypatch.setattr(yearly, "fetch_scoreboard_games", games)
    monkeypatch.setattr(yearly, "fetch_scoreboard_players", players)
    for hour in (12, 13):
        now = now.replace(hour=hour)
        result = yearly.run(tmp_path, pipeline_name="leaguepedia_active_players")
        assert result["coverage_complete_as_observed"] is True
    objects = s3.list_objects_v2(Bucket="ci-live", Prefix="bronze/leaguepedia/scoreboard_players/")
    assert objects["KeyCount"] >= 2
    subprocess.run([
        "dbt", "build", "--select", "tag:leaguepedia_active", "+gold_pro_champion_draft_by_patch", "--indirect-selection", "cautious",
        "--project-dir", str(ROOT / "dbt"), "--profiles-dir", str(ROOT / "dbt/profiles"),
        "--target-path", str(tmp_path / "target"), "--log-path", str(tmp_path / "logs"),
    ], check=True, timeout=180, cwd=ROOT)
    with conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM gold.gold_pro_player_games WHERE game_id LIKE 'CI-LP-%'")
        assert cur.fetchone()[0] == 4  # Replays do not double-count participations.
        cur.execute("""SELECT games, wins, winrate FROM gold.gold_pro_active_players_year
                       WHERE player_page='CI Pro' AND season_year=2026""")
        games_count, wins, winrate = cur.fetchone()
        assert (games_count, wins, float(winrate)) == (2, 1, 0.5)
        cur.execute("SELECT kda FROM gold.gold_pro_player_comparison WHERE player_page='CI Pro'")
        assert float(cur.fetchone()[0]) == 5.0
        cur.execute("""SELECT games_with_result, winrate, avg_deaths, kda
                       FROM gold.gold_pro_player_comparison WHERE player_page='CI Missing Stats'""")
        assert cur.fetchone() == (0, None, None, None)
    db.engine.cache_clear()
    try:
        with TestClient(app) as client:
            patches=client.get('/api/pro/draft/patches')
            assert patches.status_code == 200 and {'patch':'16.1'} in patches.json()
            draft=client.get('/api/pro/draft', params={'patch':'16.1'})
            assert draft.status_code == 200 and draft.json()
            group=client.get('/api/pro/compare', params={'year':2026,'selected_players':['CI Pro','CI Missing Stats']})
            assert group.status_code == 200 and len(group.json()) == 2
            role=client.get('/api/pro/players', params={'year':2026,'role':'Mid'})
            assert role.status_code == 200 and [p['player_page'] for p in role.json()] == ['CI Pro']
            params={'year':2026,'player_a':'CI Pro','player_b':'CI Missing Stats','region':'Europe'}
            result=client.get('/api/pro/compare',params=params)
            assert result.status_code==200 and len(result.json())==2
            pro=next(r for r in result.json() if r['player_page']=='CI Pro')
            assert pro['games']==2 and float(pro['avg_gold'])==12000
            assert float(pro['gold_min'])==400 and pro['games_with_gold_min']==2
            empty=next(r for r in result.json() if r['player_page']=='CI Missing Stats')
            assert empty['avg_gold'] is None and empty['games_with_gold']==0
            history=client.get('/api/pro/history',params=params)
            assert history.status_code==200
            assert any(r['items']=='Item A;Item B' for r in history.json())
            assert next(r for r in history.json() if r['player_page']=='CI Pro')['equipment_fields_collected'] is True
            assert next(r for r in history.json() if r['player_page']=='CI Missing Stats')['equipment_fields_collected'] is False
            assert client.get('/api/pro/compare',params={**params,'region':'Korea'}).json()==[]
            assert client.get('/api/pro/players',params={'year':2026,'champion':'Azir'}).json()[0]['player_page']=='CI Pro'
            coach = client.get('/api/pro/coaching', params={'source':'pro','player':'CI Pro','year':2026})
            assert coach.status_code == 200
            assert coach.json()[0]['games'] == 2
            assert float(coach.json()[0]['gold_min']) == 400
            accounts = client.get('/api/pro/accounts', params={'player':'CI Pro','year':2026})
            assert accounts.status_code == 200
            assert accounts.json()[0]['reported_accounts'] == 'Example#EUW'
            solo = client.get('/api/pro/coaching', params={'source':'soloq','player':'ci-p1','year':2026})
            assert solo.status_code == 200
            assert solo.json()[0]['games'] == 2
            absent = client.get('/api/pro/coaching', params={'source':'soloq','player':'ci-p1','year':2001})
            assert absent.json()[0]['games'] == 0
            assert absent.json()[0]['gold_min'] is None
    finally:
        db.engine().dispose()
        db.engine.cache_clear()
