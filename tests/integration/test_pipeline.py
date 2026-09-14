"""Real SQL/MinIO/dbt/Spark; only the external Riot API is simulated."""
import json
import time
from threading import Thread
from urllib.request import Request, urlopen

import pytest
from fastapi.testclient import TestClient
from psycopg2 import errors

from jobs.riot import live_roster, live_service
from jobs.riot.euw_ingest import get_minio_config


def test_dbt_and_readonly_api(infrastructure):
    from backend import db
    from backend.main import app

    db.engine.cache_clear()
    assert db.query("SELECT count(*) AS n FROM gold.fact_match_participant")[0]["n"] == 20
    with TestClient(app) as client:
        result = client.get("/api/data/history", params={"patch":"26.18","player":"ci-p1"})
        assert result.status_code == 200 and len(result.json()) == 2
    with pytest.raises(Exception) as exc:
        db.query("DELETE FROM gold.fact_match_participant")
    assert isinstance(exc.value.orig, (errors.ReadOnlySqlTransaction, errors.InsufficientPrivilege))
    db.engine().dispose()
    db.engine.cache_clear()


def test_display_riot_ids_not_puuids(infrastructure):
    from backend import db
    from backend.main import app

    conn, _ = infrastructure
    with conn, conn.cursor() as cur:
        for number in (1, 10):
            cur.execute("""INSERT INTO audit.riot_tracked_players
                (puuid,region,first_seen_master_plus_at,last_seen_master_plus_at)
                VALUES (%s,'euw1',now(),now()) ON CONFLICT(puuid) DO NOTHING""", (f"ci-p{number}",))
    db.engine.cache_clear()
    try:
        with TestClient(app) as client:
            response = client.get("/api/players")
            assert response.status_code == 200
            names = {r["puuid"]:r["player_name"] for r in response.json()}
            assert names["ci-p1"] == "Player1#EUW"
            assert names["ci-p10"] == "Pseudo indisponible"
    finally:
        db.engine().dispose()
        db.engine.cache_clear()
def test_coach_to_collector_to_minio_and_api(infrastructure, monkeypatch):
    from backend import db
    from backend.main import app

    conn, s3 = infrastructure
    live_service.init_schema(conn)
    monkeypatch.setattr(live_roster, "resolve", lambda _: ("ci-live-player", "CoachPlayer#EUW"))
    server = live_roster.ThreadingHTTPServer(("127.0.0.1", 0), live_roster.Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("RIOT_LIVE_SERVICE_URL", f"http://127.0.0.1:{server.server_port}")
    game = {"gameId":987654321,"gameQueueConfigId":420,"gameStartTime":1789300000000,
            "participants":[{"championId":1,"teamId":100},{"championId":2,"teamId":200}],
            "observers":{"encryptionKey":"ci-observer-secret"}}
    monkeypatch.setattr(live_service, "get_active_game_by_puuid", lambda *a, **kw: game)

    class NoWait:
        def is_set(self):
            return False

        def wait(self, _):
            return False

    db.engine.cache_clear()
    try:
        with TestClient(app) as client:
            headers = {"X-MyLeague-Action":"roster"}
            added = client.post("/api/live/roster", json={"riot_id":"CoachPlayer#EUW"}, headers=headers)
            assert added.status_code == 200
            player_id = added.json()["id"]
            with conn.cursor() as cur:
                cur.execute("""SELECT riot_summoner_name, is_tracked, is_currently_master_plus,
                    tracking_source FROM audit.riot_tracked_players WHERE puuid='ci-live-player'""")
                assert cur.fetchone() == ("CoachPlayer#EUW", True, False, "club")
            assert client.get("/api/live/roster").json()["players"][0]["riot_id"] == "CoachPlayer#EUW"
            mine = client.get('/api/my-players')
            assert mine.status_code == 200
            assert [p['puuid'] for p in mine.json()] == ['ci-live-player']
            assert mine.json()[0]['collected_games'] == 0
            # Membership, not tracking_source, is authoritative (ladder players too).
            with conn, conn.cursor() as cur:
                cur.execute("UPDATE audit.riot_tracked_players SET tracking_source='live' WHERE puuid='ci-live-player'")
            assert client.get('/api/my-players').json() == mine.json()
            for _ in range(2):
                live_service.poll_cycle(conn, get_minio_config(), NoWait(), 60, 5)
            response = client.get("/api/live/players")
            assert response.status_code == 200
            assert response.json()[0]["status"] == "in_game"
            assert "ci-observer-secret" not in response.text and "ci-live-player" not in response.text
            archived = s3.get_object(Bucket="ci-live", Key="bronze/riot/live_games/game_id=987654321/active_game.json")
            assert json.loads(archived["Body"].read())["gameId"] == game["gameId"]
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM raw.riot_live_game_snapshots WHERE game_id=987654321")
                assert cur.fetchone()[0] == 1
            assert client.delete(f"/api/live/roster/{player_id}", headers=headers).status_code == 200
            assert client.get("/api/live/players").json() == []
            assert client.get('/api/my-players').json() == []
            with conn.cursor() as cur:
                cur.execute("SELECT observed_puuid FROM raw.riot_live_game_snapshots WHERE game_id=987654321")
                assert cur.fetchone() == ("ci-live-player",)
            conn.commit()
            # Simulate a roster created by the previous release without a registry entry.
            with conn, conn.cursor() as cur:
                cur.execute("INSERT INTO raw.riot_live_roster(puuid,riot_id) VALUES ('ci-repair','Repair#EUW')")
            live_service.init_schema(conn)
            live_service.init_schema(conn)  # Idempotent migration, no duplicate identities.
            with conn.cursor() as cur:
                cur.execute("SELECT is_tracked,tracking_source FROM audit.riot_tracked_players WHERE puuid='ci-repair'")
                assert cur.fetchone() == (True, "club")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        db.engine().dispose()
        db.engine.cache_clear()


def test_spark_two_executors_publish_matchups(infrastructure):
    conn, _ = infrastructure
    for attempt in range(60):
        try:
            with urlopen("http://127.0.0.1:28090/health", timeout=2):
                break
        except OSError:
            if attempt == 59:
                raise
            time.sleep(1)
    # Production launcher/job require two registered executors, real JDBC input and SQL output.
    with urlopen(Request("http://127.0.0.1:28090/run", data=b"", method="POST"), timeout=1260) as response:
        assert response.status == 200
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), min(games), max(games), min(win_rate), max(win_rate) FROM gold.spark_champion_matchups")
        assert cur.fetchone() == (10, 2, 2, 0.5, 0.5)
        cur.execute("SELECT input_rows,output_rows,partitions FROM audit.spark_matchup_runs ORDER BY completed_at DESC LIMIT 1")
        assert cur.fetchone() == (20, 10, 4)
