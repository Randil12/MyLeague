"""Real MinIO -> raw -> dbt analytics; only external Cargo responses are simulated."""
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from jobs.leaguepedia import yearly

ROOT = Path(__file__).resolve().parents[2]


def test_annual_player_pipeline(infrastructure, monkeypatch, tmp_path):
    conn, s3 = infrastructure
    now = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(yearly.ingest, "utc_now", lambda: now)
    monkeypatch.setattr(yearly.ingest, "get_client", lambda: object())

    def games(client, lower, **kwargs):
        day = lower[:10]
        return [{"GameId": f"CI-LP-{day}", "Patch": "26.1", "DateTime_UTC": lower,
                 "Tournament": "CI Cup", "OverviewPage": "CI/2026", "Team1": "A",
                 "Team2": "B", "WinTeam": "A" if day.endswith("01") else "B"}]

    def players(client, lower, **kwargs):
        return [{"GameId": f"CI-LP-{lower[:10]}", "Link": "CI Pro", "Team": "A",
                 "Role": "Mid", "Champion": "Azir", "DateTime_UTC": lower,
                 "Kills": "4", "Deaths": "2", "Assists": "6", "CS": "200", "Gold": "12000"},
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
        "dbt", "build", "--select", "tag:leaguepedia_active", "--indirect-selection", "cautious",
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
