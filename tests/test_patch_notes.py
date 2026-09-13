"""Tests unitaires du scraping des notes de patch (sans réseau)."""

import pytest

from jobs.patch_notes.scraper import (
    build_patch_notes_url,
    parse_patch_notes,
    patch_from_version,
    patch_slug,
)


def test_patch_from_version():
    assert patch_from_version("16.13.1") == "16.13"
    assert patch_from_version("16.1.695.9999") == "16.1"
    with pytest.raises(ValueError):
        patch_from_version("16")


def test_patch_slug_uses_year_numbering(monkeypatch):
    # Data Dragon compte en saisons (16.x), le site des notes en années (26.x)
    monkeypatch.delenv("PATCH_NOTES_SLUG_OFFSET", raising=False)
    assert patch_slug("16.13") == "26-13"
    assert patch_slug("16.1") == "26-1"


def test_patch_slug_offset_override(monkeypatch):
    monkeypatch.setenv("PATCH_NOTES_SLUG_OFFSET", "0")
    assert patch_slug("16.13") == "16-13"


def test_build_patch_notes_url_slug(monkeypatch):
    monkeypatch.delenv("PATCH_NOTES_URL_TEMPLATE", raising=False)
    monkeypatch.delenv("PATCH_NOTES_SLUG_OFFSET", raising=False)
    url = build_patch_notes_url("16.13", locale="fr-fr")
    assert url == (
        "https://www.leagueoflegends.com/fr-fr/news/game-updates/"
        "league-of-legends-patch-26-13-notes/"
    )


def test_build_patch_notes_url_template_override(monkeypatch):
    monkeypatch.setenv("PATCH_NOTES_URL_TEMPLATE", "https://example.com/{locale}/{slug}")
    monkeypatch.delenv("PATCH_NOTES_SLUG_OFFSET", raising=False)
    assert build_patch_notes_url("16.13", locale="en-us") == "https://example.com/en-us/26-13"


SAMPLE_HTML = """
<html><body><main>
  <h1>Notes de patch 16.13</h1>
  <p>Texte d'introduction du patch.</p>
  <h2>Champions</h2>
  <h3>Aatrox</h3>
  <p>Dégâts de base du Q réduits.</p>
  <li>Q : 70 &gt; 60</li>
  <h3>Zeri</h3>
  <p>Vitesse d'attaque augmentée.</p>
  <h2>Objets</h2>
  <h3>Soif-de-sang</h3>
  <p>Vol de vie réduit.</p>
  <h3>Section vide</h3>
</main></body></html>
"""


def test_parse_patch_notes_extracts_sections():
    parsed = parse_patch_notes(SAMPLE_HTML)
    assert parsed["title"] == "Notes de patch 16.13"

    headings = [s["heading"] for s in parsed["sections"]]
    assert "Aatrox" in headings
    assert "Zeri" in headings
    assert "Soif-de-sang" in headings
    # une section sans texte est écartée
    assert "Section vide" not in headings

    aatrox = next(s for s in parsed["sections"] if s["heading"] == "Aatrox")
    assert "Dégâts de base" in aatrox["text"]
    assert "70 > 60" in aatrox["text"]
    assert aatrox["level"] == "h3"


def test_parse_patch_notes_handles_empty_page():
    parsed = parse_patch_notes("<html><body></body></html>")
    assert parsed["title"] is None
    assert parsed["sections"] == []
