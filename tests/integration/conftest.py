"""Opt-in disposable infrastructure. Fixed addresses prevent accidental production writes."""
import json
import os
import subprocess
import time
from pathlib import Path

import boto3
import psycopg2
import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session", autouse=True)
def infrastructure(tmp_path_factory):
    if os.getenv("RUN_INTEGRATION_TESTS") != "1":
        pytest.skip("Requires isolated compose.ci.yml stack and RUN_INTEGRATION_TESTS=1")
    with pytest.MonkeyPatch.context() as patch:
        values = {
            "GOLD_POSTGRES_HOST":"127.0.0.1", "GOLD_POSTGRES_PORT":"25432",
            "GOLD_POSTGRES_DB":"myleague_ci", "GOLD_POSTGRES_USER":"gold",
            "GOLD_POSTGRES_PASSWORD":"ci-only-password", "DATA_ANALYST_USER":"data_analyst",
            "DATA_ANALYST_PASSWORD":"ci-analyst-password", "RIOT_API_KEY":"ci-not-a-real-key",
            "MINIO_ENDPOINT_URL":"http://127.0.0.1:29000", "MINIO_BUCKET":"ci-live",
            "AWS_ACCESS_KEY_ID":"ci-minio", "AWS_SECRET_ACCESS_KEY":"ci-minio-password",
            "AWS_DEFAULT_REGION":"eu-west-3", "RIOT_LIVE_STREAM_MAX_PLAYERS":"5",
        }
        for key, value in values.items():
            patch.setenv(key, value)
        conn = psycopg2.connect(host="127.0.0.1", port=25432, dbname="myleague_ci",
                                user="gold", password="ci-only-password", connect_timeout=5)
        try:
            with conn, conn.cursor() as cur:
                cur.execute("SELECT current_database()")
                assert cur.fetchone()[0] == "myleague_ci"
                cur.execute((ROOT / "postgres/init_gold.sql").read_text(encoding="utf-8-sig"))
                cur.execute("""DO $$ BEGIN
                    IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='data_analyst') THEN
                        CREATE ROLE data_analyst LOGIN PASSWORD 'ci-analyst-password';
                    END IF;
                    END $$;
                    GRANT USAGE ON SCHEMA gold,reference,audit TO data_analyst;
                    GRANT SELECT ON ALL TABLES IN SCHEMA gold,reference,audit TO data_analyst;
                    ALTER DEFAULT PRIVILEGES IN SCHEMA gold,reference,audit GRANT SELECT ON TABLES TO data_analyst;
                """)
                roles = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
                for match in (1, 2):
                    participants = [{"puuid":f"ci-p{i}", "championId":i, "championName":f"Champion{i}",
                        "teamId":100 if i<=5 else 200, "teamPosition":roles[(i-1)%5],
                        "win": (i<=5) == (match==1), "kills":3, "deaths":2, "assists":4,
                        "goldEarned":10000+i*100, "totalMinionsKilled":100+i,
                        "visionScore":20, "totalDamageDealtToChampions":12000,
                        "riotIdGameName":f"Player{i}" if i<10 else None,
                        "riotIdTagline":"EUW" if i<10 else None}
                        for i in range(1,11)]
                    payload = {"info":{"queueId":420,"gameVersion":"26.18.1", "gameDuration":1800,
                        "gameCreation":1789300000000, "participants":participants}}
                    cur.execute("""INSERT INTO raw.riot_matches(match_id,region,payload)
                        VALUES (%s,'euw1',%s) ON CONFLICT(match_id) DO UPDATE SET payload=EXCLUDED.payload""",
                                (f"CI_{match}", json.dumps(payload)))
            artifacts = tmp_path_factory.mktemp("dbt")
            subprocess.run(["dbt", "build", "--select", "+fact_match_participant", "gold_player_names",
                "--project-dir", str(ROOT/"dbt"), "--profiles-dir", str(ROOT/"dbt/profiles"),
                "--target-path", str(artifacts/"target"), "--log-path", str(artifacts/"logs")],
                check=True, timeout=180, cwd=ROOT)
            s3 = boto3.client("s3", endpoint_url=values["MINIO_ENDPOINT_URL"],
                aws_access_key_id="ci-minio", aws_secret_access_key="ci-minio-password",
                region_name="eu-west-3")
            for attempt in range(30):
                try:
                    buckets = s3.list_buckets()
                    break
                except Exception:
                    if attempt == 29:
                        raise
                    time.sleep(1)
            if "ci-live" not in [b["Name"] for b in buckets["Buckets"]]:
                s3.create_bucket(Bucket="ci-live")
            yield conn, s3
        finally:
            conn.close()
