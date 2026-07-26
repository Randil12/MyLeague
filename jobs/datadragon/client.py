from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import urlopen

DATA_DRAGON_BASE_URL = "https://ddragon.leagueoflegends.com"


def fetch_json(url: str) -> Any:
    with urlopen(url, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset))


def get_versions() -> list[str]:
    versions = fetch_json(f"{DATA_DRAGON_BASE_URL}/api/versions.json")
    if not isinstance(versions, list) or not versions:
        raise ValueError("Data Dragon returned an empty versions list")
    return versions


def get_latest_version() -> str:
    return get_versions()[0]


def get_champions(version: str, locale: str = "fr_FR") -> dict[str, Any]:
    return fetch_json(
        f"{DATA_DRAGON_BASE_URL}/cdn/{version}/data/{locale}/champion.json"
    )


def get_champion_detail(
    version: str,
    champion_id: str,
    locale: str = "fr_FR",
) -> dict[str, Any]:
    safe_champion_id = quote(champion_id, safe="")
    return fetch_json(
        f"{DATA_DRAGON_BASE_URL}/cdn/{version}/data/{locale}/champion/{safe_champion_id}.json"
    )


def get_items(version: str, locale: str = "fr_FR") -> dict[str, Any]:
    return fetch_json(f"{DATA_DRAGON_BASE_URL}/cdn/{version}/data/{locale}/item.json")


def get_summoner_spells(version: str, locale: str = "fr_FR") -> dict[str, Any]:
    return fetch_json(
        f"{DATA_DRAGON_BASE_URL}/cdn/{version}/data/{locale}/summoner.json"
    )


def get_runes(version: str, locale: str = "fr_FR") -> list[dict[str, Any]]:
    """Arbres de runes (runesReforged) : styles, slots et runes dont les keystones."""
    return fetch_json(
        f"{DATA_DRAGON_BASE_URL}/cdn/{version}/data/{locale}/runesReforged.json"
    )


def write_json(payload: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
