"""Private roster management endpoint; technical database credentials stay in riot-live."""
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread
from urllib.parse import quote

from jobs.riot.client import RiotApiError, fetch_json
from jobs.riot.euw_ingest import get_gold_conn

LOOKUP_LOCK = Lock()
NEXT_LOOKUP = 0.0


class RosterError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def capacity():
    return max(1, min(10, int(os.getenv("RIOT_LIVE_STREAM_MAX_PLAYERS", "5"))))


def parse_riot_id(value):
    if not isinstance(value, str) or value.count("#") != 1 or any(ord(c) < 32 for c in value):
        raise RosterError(422, "Saisis un Riot ID complet : Pseudo#TAG.")
    name, tag = (part.strip() for part in value.split("#"))
    if not 1 <= len(name) <= 32 or not 1 <= len(tag) <= 16 or any(ord(c) < 32 for c in name + tag):
        raise RosterError(422, "Riot ID invalide.")
    return name, tag


def init_roster(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS raw.riot_live_roster (
        id bigserial PRIMARY KEY, puuid text UNIQUE NOT NULL,
        riot_id text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    )""")


def resolve(value):
    global NEXT_LOOKUP
    name, tag = parse_riot_id(value)
    if not LOOKUP_LOCK.acquire(blocking=False):
        raise RosterError(429, "Une recherche est en cours. Réessaie dans quelques secondes.")
    try:
        if time.monotonic() < NEXT_LOOKUP:
            raise RosterError(429, "Recherche temporairement limitée. Réessaie plus tard.")
        NEXT_LOOKUP = time.monotonic() + 5
        try:
            account = fetch_json("https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/"
                                 + quote(name, safe="") + "/" + quote(tag, safe=""), retries=0)
            if not isinstance(account, dict) or not isinstance(account.get("puuid"), str) or not account["puuid"]:
                raise RosterError(503, "Réponse Riot incomplète.")
            # ACCOUNT-V1 is regional, not proof that the LoL account exists on EUW.
            fetch_json("https://euw1.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/"
                       + quote(account["puuid"], safe=""), retries=0)
        except RiotApiError as exc:
            if exc.status_code == 429:
                NEXT_LOOKUP = time.monotonic() + (exc.retry_after or 60)
                raise RosterError(429, "Quota Riot atteint. Réessaie après la pause API.") from None
            if exc.status_code == 404:
                raise RosterError(404, "Riot ID introuvable ou compte LoL absent d’EUW. Vérifie le pseudo et le tag.") from None
            if exc.status_code in (401, 403):
                NEXT_LOOKUP = time.monotonic() + 60
                raise RosterError(503, "Clé Riot refusée : vérifier la configuration du service.") from None
            raise RosterError(503, "Riot est indisponible. Réessaie plus tard.") from None
        return account["puuid"], f"{account.get('gameName', name)}#{account.get('tagLine', tag)}"
    finally:
        LOOKUP_LOCK.release()


def roster_request(method, path, body=None):
    conn = get_gold_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout='5s'")
                if method == "GET" and path == "/roster":
                    cur.execute("SELECT id, riot_id FROM raw.riot_live_roster ORDER BY created_at, id")
                    return {"players": [{"id": r[0], "riot_id": r[1]} for r in cur.fetchall()],
                            "limit": capacity()}
                if method == "POST" and path == "/roster":
                    value = body.get("riot_id") if isinstance(body, dict) else None
                    parse_riot_id(value)
                    # Serialize writes across processes; duplicates are resolved by immutable PUUID.
                    cur.execute("SELECT pg_advisory_xact_lock(74120503)")
                    cur.execute("SELECT count(*) FROM raw.riot_live_roster")
                    if cur.fetchone()[0] >= capacity():
                        raise RosterError(409, "Liste pleine : retire un joueur avant d’en ajouter un.")
                    puuid, riot_id = resolve(value)
                    cur.execute("""INSERT INTO raw.riot_live_roster(puuid,riot_id) VALUES (%s,%s)
                        ON CONFLICT(puuid) DO UPDATE SET riot_id=EXCLUDED.riot_id RETURNING id""", (puuid, riot_id))
                    return {"id": cur.fetchone()[0], "riot_id": riot_id}
                if method == "DELETE" and path.startswith("/roster/") and path[8:].isdigit():
                    cur.execute("SELECT pg_advisory_xact_lock(74120503)")
                    cur.execute("DELETE FROM raw.riot_live_roster WHERE id=%s", (int(path[8:]),))
                    return {"removed": True}
                raise RosterError(404, "Opération inconnue.")
    finally:
        conn.close()


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *_):
        pass  # No Riot IDs or request bodies in HTTP access logs.

    def handle_request(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 1024:
                raise RosterError(413, "Requête trop volumineuse.")
            body = json.loads(self.rfile.read(length)) if length else None
            payload, code = roster_request(self.command, self.path, body), 200
        except RosterError as exc:
            payload, code = {"detail": exc.message}, exc.status
        except (ValueError, UnicodeDecodeError):
            payload, code = {"detail": "Requête invalide."}, 422
        except Exception:
            payload, code = {"detail": "Suivi indisponible. Vérifier riot-live et PostgreSQL."}, 503
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    do_GET = handle_request
    do_POST = handle_request
    do_DELETE = handle_request


def start_server():
    server = ThreadingHTTPServer(("0.0.0.0", 8091), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    return server
