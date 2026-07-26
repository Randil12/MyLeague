"""Scraping des notes de patch officielles Riot (technique : web scraping HTML).

Complète les API : les notes de patch expliquent les variations de winrate
mesurées dans gold (corrélation nerf/buff annoncé <-> méta observée).
"""

from __future__ import annotations

import os
from typing import Any

DEFAULT_URL_TEMPLATE = (
    "https://www.leagueoflegends.com/{locale}/news/game-updates/"
    "league-of-legends-patch-{slug}-notes/"
)


def patch_from_version(version: str) -> str:
    """'16.13.1' -> '16.13'."""
    parts = version.split(".")
    if len(parts) < 2:
        raise ValueError(f"Version Data Dragon inattendue : '{version}'")
    return f"{parts[0]}.{parts[1]}"


def patch_slug(patch: str) -> str:
    """'16.13' -> '26-13'.

    Deux numérotations coexistent chez Riot : Data Dragon compte en saisons
    (saison 16 = année 2026) alors que le site des notes de patch compte en
    années (26.13). Le décalage, constant (+10), est configurable via
    PATCH_NOTES_SLUG_OFFSET si Riot changeait à nouveau de convention.
    La clé 'patch' stockée en base reste au format Data Dragon (16.13) pour
    joindre avec les patchs dérivés du gameVersion des matchs.
    """
    offset = int(os.getenv("PATCH_NOTES_SLUG_OFFSET", "10"))
    major, minor = patch.split(".", 1)
    return f"{int(major) + offset}-{minor.replace('.', '-')}"


def build_patch_notes_url(patch: str, locale: str = "fr-fr") -> str:
    """'16.13' -> .../fr-fr/news/game-updates/league-of-legends-patch-26-13-notes/"""
    template = os.getenv("PATCH_NOTES_URL_TEMPLATE", DEFAULT_URL_TEMPLATE)
    return template.format(locale=locale, slug=patch_slug(patch))


def fetch_html(url: str) -> str | None:
    """Récupère la page. None si 404 (notes pas encore publiées pour ce patch)."""
    import requests

    response = requests.get(
        url,
        headers={"User-Agent": "MyLeague-PatchNotes/1.0 (projet pedagogique)"},
        timeout=30,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.text


def parse_patch_notes(html: str) -> dict[str, Any]:
    """Extraction structurée : titre de page + sections (heading -> texte).

    Parseur volontairement générique (titres h2/h3/h4 + texte associé) pour
    résister aux changements de mise en page du site. Le HTML brut est de toute
    façon conservé en bronze : le parsing peut être rejoué a posteriori.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("h1")
    title = title_tag.get_text(" ", strip=True) if title_tag else None

    root = soup.find("main") or soup.body or soup
    sections: list[dict[str, str]] = []
    current: dict[str, str] | None = None

    for tag in root.find_all(["h2", "h3", "h4", "p", "li"]):
        if tag.name in ("h2", "h3", "h4"):
            heading = tag.get_text(" ", strip=True)
            if heading:
                current = {"heading": heading, "level": tag.name, "text": ""}
                sections.append(current)
        elif current is not None:
            text = tag.get_text(" ", strip=True)
            if text:
                current["text"] = f"{current['text']} {text}".strip()

    return {
        "title": title,
        "sections": [s for s in sections if s["text"]],
    }
