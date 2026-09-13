"""Resumable annual competition history. Checkpoints follow successful raw writes."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic

from jobs.leaguepedia import ingest
from jobs.leaguepedia.client import PaginationLimit, fetch_scoreboard_games, fetch_scoreboard_players


def windows(start, end):
    while start < end:
        stop = min(start + timedelta(days=1), end)
        yield start, stop
        start = stop


def fetch_complete(client, fetcher, start, end, max_pages):
    """Split saturated windows; never quietly drop records at the page ceiling."""
    try:
        return fetcher(client, start.strftime("%Y-%m-%d %H:%M:%S"), max_pages=max_pages,
                       until_iso=end.strftime("%Y-%m-%d %H:%M:%S"))
    except PaginationLimit:
        seconds = int((end - start).total_seconds())
        if seconds <= 1:
            raise
        middle = start + timedelta(seconds=seconds // 2)
        return (fetch_complete(client, fetcher, start, middle, max_pages)
                + fetch_complete(client, fetcher, middle, end, max_pages))


def run(raw_dir, year=None, max_pages=20, days_per_run=45, budget_seconds=900,
        revisit_after_seconds=0, pipeline_name=ingest.PIPELINE_NAME):
    now = ingest.utc_now().replace(microsecond=0)
    target_year = year or now.year
    if not 2000 <= target_year <= now.year or days_per_run < 3:
        raise ValueError("Choose a year between 2000 and the current year; days_per_run >= 3")
    start = datetime(target_year, 1, 1, tzinfo=timezone.utc)
    end = min(now, datetime(target_year + 1, 1, 1, tzinfo=timezone.utc))
    periods = list(windows(start, end))
    conn = ingest.get_gold_conn()
    run_id = "yearly-" + now.strftime("%Y%m%dT%H%M%S%fZ")
    completed = read = written = 0
    started = False
    deadline = monotonic() + budget_seconds
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(74120504)")
            if not cur.fetchone()[0]:
                raise RuntimeError("Another Leaguepedia annual collector is already running")
        ingest.init_leaguepedia_schema(conn)
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS audit.leaguepedia_year_days (
                day date PRIMARY KEY, checked_at timestamptz NOT NULL,
                games_rows integer NOT NULL, player_rows integer NOT NULL
            )""")
            cur.execute("SELECT day, checked_at FROM audit.leaguepedia_year_days WHERE day >= %s AND day < %s",
                        (start.date(), datetime(target_year + 1, 1, 1).date()))
            checked = dict(cur.fetchall())
        conn.commit()
        ingest.start_run(conn, run_id, pipeline_name)
        started = True
        client = ingest.get_client()
        config = ingest.get_minio_config()
        # Refresh recent days first; then fill missing history, then revisit oldest checks.
        recent = periods[-2:] if target_year == now.year else []
        recent_dates = {a.date() for a, _ in recent}
        older = [p for p in periods if p[0].date() not in recent_dates]
        older = [p for p in older if p[0].date() not in checked
                 or (now - checked[p[0].date()]).total_seconds() >= revisit_after_seconds]
        older.sort(key=lambda p: (p[0].date() in checked,
                                 checked.get(p[0].date(), start), p[0]))
        for lower, upper in (recent + older)[:days_per_run]:
            if monotonic() >= deadline:
                break
            games = fetch_complete(client, fetch_scoreboard_games, lower, upper, max_pages)
            players = fetch_complete(client, fetch_scoreboard_players, lower, upper, max_pages)
            read += len(games) + len(players)
            day_run = f"{run_id}/day={lower.date()}"
            for name, rows in (("scoreboard_games", games), ("scoreboard_players", players)):
                ingest.save_bronze(rows, name, day_run, Path(raw_dir), ingest.DEFAULT_MINIO_PREFIX, config)
            game_count = ingest.upsert_scoreboard_games(conn, games)
            player_count = ingest.upsert_scoreboard_players(conn, players)
            written += game_count + player_count
            if game_count != len(games) or player_count != len(players):
                raise RuntimeError(f"Incomplete raw load for {lower.date()}; day will be retried")
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO audit.leaguepedia_year_days VALUES (%s,%s,%s,%s)
                    ON CONFLICT (day) DO UPDATE SET checked_at=EXCLUDED.checked_at,
                    games_rows=EXCLUDED.games_rows, player_rows=EXCLUDED.player_rows""",
                            (lower.date(), now, game_count, player_count))
            conn.commit()
            checked[lower.date()] = now
            completed += 1
        ingest.finish_run(conn, run_id, "success", read, written, 0)
        missing = sum(a.date() not in checked for a, _ in periods)
        return {"year": target_year, "days_processed": completed, "days_remaining": missing,
                "coverage_complete_as_observed": missing == 0, "records_written": written}
    except Exception:
        conn.rollback()
        if started:
            ingest.finish_run(conn, run_id, "failed", read, written, 1)
        raise
    finally:
        conn.close()
