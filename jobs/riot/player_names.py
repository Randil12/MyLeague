"""Resolve Challenger Riot IDs once a week; never query Riot from page rendering."""
import time
from urllib.parse import quote

from jobs.riot.client import RiotApiError, fetch_json
from jobs.riot.euw_ingest import get_gold_conn


def run():
    conn = get_gold_conn()
    updated = 0
    deadline = time.monotonic() + 720
    try:
        with conn, conn.cursor() as cur:
            cur.execute("ALTER TABLE audit.riot_tracked_players ADD COLUMN IF NOT EXISTS name_checked_at timestamptz")
            cur.execute("""SELECT puuid FROM audit.riot_tracked_players
                WHERE region='euw1' AND tier='CHALLENGER' AND is_currently_master_plus
                  AND (name_checked_at IS NULL OR name_checked_at < now()-interval '7 days')
                ORDER BY name_checked_at NULLS FIRST, league_points DESC LIMIT 300""")
            players = [row[0] for row in cur.fetchall()]
        for puuid in players:
            if time.monotonic() >= deadline:
                break
            time.sleep(2)
            try:
                account = fetch_json("https://europe.api.riotgames.com/riot/account/v1/accounts/by-puuid/"
                                     + quote(puuid, safe=""), retries=0)
            except RiotApiError as exc:
                # Stop this batch on quota/auth/outage; preserve names already resolved.
                return {"updated": updated, "status": "deferred", "http_status": exc.status_code}
            if not isinstance(account, dict) or not account.get("gameName") or not account.get("tagLine"):
                continue
            with conn, conn.cursor() as cur:
                cur.execute("""UPDATE audit.riot_tracked_players
                    SET riot_summoner_name=%s, name_checked_at=now() WHERE puuid=%s""",
                            (f"{account['gameName']}#{account['tagLine']}", puuid))
            updated += 1
        return {"updated": updated, "remaining": len(players)-updated, "status": "ok"}
    finally:
        conn.close()
