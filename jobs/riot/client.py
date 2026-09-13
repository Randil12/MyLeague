from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

EUW_PLATFORM_BASE_URL = "https://euw1.api.riotgames.com"
EUROPE_REGIONAL_BASE_URL = "https://europe.api.riotgames.com"
RANKED_SOLO_QUEUE = "RANKED_SOLO_5x5"


class RiotApiError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def get_api_key() -> str:
    raw_api_key = os.getenv("RIOT_API_KEY")
    if not raw_api_key:
        raise RiotApiError("RIOT_API_KEY is missing in the Airflow container environment")

    api_key = raw_api_key.strip().strip('"').strip("'")
    if not api_key:
        raise RiotApiError("RIOT_API_KEY is empty after trimming whitespace/quotes")
    if api_key == "${RIOT_API_KEY}" or not api_key.startswith("RGAPI-"):
        raise RiotApiError("RIOT_API_KEY is loaded but does not look like a Riot development key")
    return api_key


def get_api_key_fingerprint(api_key: str | None = None) -> str:
    key = api_key or get_api_key()
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]
    return f"len={len(key)} sha256_prefix={digest}"


def build_headers(api_key: str | None = None) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "User-Agent": "MyLeague-Airflow/1.0",
        "X-Riot-Token": api_key or get_api_key(),
    }


def fetch_json(url: str, api_key: str | None = None, retries: int = 3) -> Any:
    headers = build_headers(api_key)
    for attempt in range(retries + 1):
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=30) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return json.loads(response.read().decode(charset))
        except HTTPError as exc:
            if exc.code == 429 and attempt < retries:
                retry_after = int(exc.headers.get("Retry-After", "2"))
                time.sleep(retry_after)
                continue
            if 500 <= exc.code < 600 and attempt < retries:
                time.sleep(2**attempt)
                continue

            body = exc.read().decode("utf-8", errors="replace")
            if exc.code in {401, 403}:
                key_info = get_api_key_fingerprint(headers["X-Riot-Token"])
                raise RiotApiError(
                    f"Riot API authentication failed ({exc.code}) for {url}: {body}. "
                    f"Loaded RIOT_API_KEY {key_info}. "
                    "Regenerate the key in Riot Developer Portal and recreate the Airflow container.",
                    status_code=exc.code,
                ) from exc
            raise RiotApiError(
                f"Riot API error {exc.code} for {url}: {body}", status_code=exc.code
            ) from exc

    raise RiotApiError(f"Riot API request failed after retries: {url}")


def get_apex_league(tier: str, queue: str = RANKED_SOLO_QUEUE) -> dict[str, Any]:
    tier_path = tier.lower()
    url = f"{EUW_PLATFORM_BASE_URL}/lol/league/v4/{tier_path}leagues/by-queue/{queue}"
    return fetch_json(url)


def get_master_plus_entries(queue: str = RANKED_SOLO_QUEUE) -> list[dict[str, Any]]:
    entries = []
    for tier in ["challenger", "grandmaster", "master"]:
        league = get_apex_league(tier, queue)
        for entry in league.get("entries", []):
            entries.append({**entry, "tier": tier.upper(), "queueType": queue})
    return entries


def get_summoner_by_id(encrypted_summoner_id: str) -> dict[str, Any]:
    url = f"{EUW_PLATFORM_BASE_URL}/lol/summoner/v4/summoners/{encrypted_summoner_id}"
    return fetch_json(url)


def get_match_ids_by_puuid(
    puuid: str,
    start_time: int,
    end_time: int,
    queue: int = 420,
    count: int = 20,
) -> list[str]:
    query = urlencode(
        {
            "startTime": start_time,
            "endTime": end_time,
            "queue": queue,
            "start": 0,
            "count": min(count, 100),
        }
    )
    url = f"{EUROPE_REGIONAL_BASE_URL}/lol/match/v5/matches/by-puuid/{puuid}/ids?{query}"
    return fetch_json(url)


def get_match(match_id: str) -> dict[str, Any]:
    url = f"{EUROPE_REGIONAL_BASE_URL}/lol/match/v5/matches/{match_id}"
    return fetch_json(url)


def get_match_timeline(match_id: str) -> dict[str, Any]:
    """Timeline minute par minute d'un match (gold, XP, kills, wards, objectifs)."""
    url = f"{EUROPE_REGIONAL_BASE_URL}/lol/match/v5/matches/{match_id}/timeline"
    return fetch_json(url)


def get_league_entries(
    tier: str,
    division: str = "I",
    queue: str = RANKED_SOLO_QUEUE,
    page: int = 1,
) -> list[dict[str, Any]]:
    """Entrées de ligue pour les tiers non-apex (DIAMOND, EMERALD, ..., IRON)."""
    url = (
        f"{EUW_PLATFORM_BASE_URL}/lol/league/v4/entries/"
        f"{queue}/{tier.upper()}/{division.upper()}?page={page}"
    )
    return fetch_json(url)


def get_active_game_by_puuid(puuid: str) -> dict[str, Any] | None:
    """Partie en cours d'un joueur (spectator-v5). None si le joueur n'est pas en partie."""
    url = f"{EUW_PLATFORM_BASE_URL}/lol/spectator/v5/active-games/by-summoner/{puuid}"
    try:
        return fetch_json(url)
    except RiotApiError as exc:
        if exc.status_code == 404:
            return None
        raise


def get_account_by_riot_id(game_name: str, tag_line: str) -> dict[str, Any]:
    """Résolution Riot ID (GameName#TAG) -> puuid via account-v1."""
    url = (
        f"{EUROPE_REGIONAL_BASE_URL}/riot/account/v1/accounts/by-riot-id/"
        f"{quote(game_name, safe='')}/{quote(tag_line, safe='')}"
    )
    return fetch_json(url)


def get_champion_masteries_by_puuid(puuid: str) -> list[dict[str, Any]]:
    """Maîtrise de champions d'un joueur (pool de champions, points, niveau)."""
    url = f"{EUW_PLATFORM_BASE_URL}/lol/champion-mastery/v4/champion-masteries/by-puuid/{puuid}"
    return fetch_json(url)


def write_json(payload: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

