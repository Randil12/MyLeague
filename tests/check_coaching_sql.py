"""Validate new SQL on a disposable PostgreSQL container, never the user's database.

Usage: python -m tests.check_coaching_sql is not required; invoke this file with
PYTHONPATH=. and the full ID of an isolated, empty postgres:15 test container.
"""
import re
import subprocess
import sys
import time

from backend import queries


def main(container_id):
    if not re.fullmatch(r"[0-9a-f]{64}", container_id):
        raise ValueError("Expected full disposable container ID")
    cmd = ["docker", "exec", "-i", container_id, "psql", "-h", "127.0.0.1",
           "-U", "postgres", "-v", "ON_ERROR_STOP=1"]
    for _ in range(30):
        check = subprocess.run(cmd + ["-c", "SELECT 1"], capture_output=True)
        if check.returncode == 0:
            break
        time.sleep(.3)
    else:
        raise RuntimeError("Test PostgreSQL did not start")
    fixture = """
    BEGIN;
    CREATE SCHEMA gold;
    CREATE TABLE gold.fact_match_participant (
      match_id text, puuid text, champion_name text, team_id int, team_position text,
      patch text, win bool, kills int, deaths int, assists int, total_cs int,
      gold_earned int, damage_to_champions int, vision_score int,
      game_duration_s int, game_started_at timestamptz
    );
    INSERT INTO gold.fact_match_participant
    SELECT 'match' || m, CASE WHEN m=3 AND i=3 THEN 'replacement' ELSE 'p'||i END,
      'A'||i, CASE WHEN i<=5 THEN 100 ELSE 200 END,
      CASE WHEN m=3 THEN 'TOP' ELSE (ARRAY['TOP','JUNGLE','MIDDLE','BOTTOM','UTILITY'])[(i-1)%5+1] END,
      '16.1', i<=5, 3, 2, 4, 100+i, 1000*i, 500*i, 20, 1800,
      '2026-09-13T12:00:00Z'::timestamptz + m * interval '1 hour'
    FROM generate_series(1,3) m CROSS JOIN generate_series(1,10) i;
    """
    params = {"patch": "'16.1'", "player": "'p1'", "champion": "'A1'", "role": "'TOP'",
              "minimum": "1", "roster": "ARRAY['p1','p2','p3','p4','p5']"}

    def bind(sql):
        return re.sub(r"(?<!:):([a-z_]+)", lambda m: params[m[1]], sql)

    for name in ["matchups", "flex", "compositions", "player_matchups", "player_summary",
                 "history", "progress", "durations"]:
        fixture += f"CREATE TEMP TABLE result_{name} AS {bind(queries.DATASETS[name])};\n"
    fixture += f"CREATE TEMP TABLE result_team AS {bind(queries.TEAM)};\n"
    fixture += """
    DO $$ BEGIN
      ASSERT (SELECT count(*) FROM result_matchups) = 1, 'Ambiguous roles must be excluded';
      ASSERT (SELECT games FROM result_matchups) = 2, 'Exactly two valid matchups';
      ASSERT (SELECT gold_delta FROM result_matchups) = -5000, 'Correct opponent pairing';
      ASSERT (SELECT count(*) FROM result_compositions) = 2, 'Exactly two valid compositions';
      ASSERT (SELECT min(games) FROM result_compositions) = 2, 'Compositions grouped across matches';
      ASSERT (SELECT count(*) FROM result_team) = 2, 'Replacement player must break full-roster match';
      ASSERT (SELECT games FROM result_player_summary) = 3, 'Individual history keeps all three matches';
    END $$;
    ROLLBACK;
    """
    result = subprocess.run(cmd, input=fixture, text=True, encoding="utf-8", capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr)
    print("9 SQL queries executed; pairing, compositions and same-side roster assertions passed.")


if __name__ == "__main__":
    main(sys.argv[1])
