from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


EUW_PLATFORM_BASE_URL = "https://euw1.api.riotgames.com"
EUROPE_REGIONAL_BASE_URL = "https://europe.api.riotgames.com"
RANKED_SOLO_QUEUE = "RANKED_SOLO_5x5"


class RiotApiError(RuntimeError):
    pass


def get_api_key() -> str:
    api_key = os.getenv("RIOT_API_KEY")
    if not api_key:
        raise RiotApiError("RIOT_API_KEY is missing")
    return api_key


def fetch_json(url: str, api_key: str | None = None, retries: int = 3) -> Any:
    headers = {"X-Riot-Token": api_key or get_api_key()}

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
            raise RiotApiError(f"Riot API error {exc.code} for {url}: {body}") from exc

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


def write_json(payload: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
