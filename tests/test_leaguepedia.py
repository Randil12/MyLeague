"""Tests unitaires Leaguepedia (sans réseau ni BDD ni mwrogue)."""

import pytest

from jobs.leaguepedia.client import LeaguepediaError, get_credentials
from jobs.leaguepedia.ingest import extract_game, extract_player_game, field


def test_field_handles_cargo_space_rename():
    row = {"GameId": "g1", "DateTime UTC": "2026-07-01 18:00:00"}
    assert field(row, "GameId") == "g1"
    # Cargo renvoie 'DateTime UTC' quand on demande 'DateTime_UTC'
    assert field(row, "DateTime_UTC") == "2026-07-01 18:00:00"
    assert field(row, "Patch") is None


def test_extract_game_normalizes_row():
    row = {"GameId": "LPL/2026/g42", "Patch": "16.13", "DateTime UTC": "2026-07-01 18:00:00"}
    game = extract_game(row)
    assert game == {
        "game_id": "LPL/2026/g42",
        "patch": "16.13",
        "game_date": "2026-07-01 18:00:00",
    }


def test_extract_game_rejects_missing_id():
    assert extract_game({"Patch": "16.13"}) is None
    assert extract_game({}) is None


def test_extract_game_empty_patch_becomes_none():
    game = extract_game({"GameId": "g1", "Patch": ""})
    assert game is not None and game["patch"] is None


def test_extract_player_game_composite_key():
    row = {
        "GameId": "LEC/2026/g7",
        "Link": "Faker",
        "Champion": "Azir",
        "Role": "Mid",
        "DateTime UTC": "2026-07-02 19:00:00",
    }
    player_game = extract_player_game(row)
    assert player_game == {
        "game_id": "LEC/2026/g7",
        "player_page": "Faker",
        "champion": "Azir",
        "role": "Mid",
        "game_date": "2026-07-02 19:00:00",
    }
    # sans identifiant de joueur ou de partie : rejeté
    assert extract_player_game({"GameId": "g1"}) is None
    assert extract_player_game({"Link": "Faker"}) is None


def test_get_credentials_requires_env(monkeypatch):
    monkeypatch.delenv("LEAGUEPEDIA_USERNAME", raising=False)
    monkeypatch.delenv("LEAGUEPEDIA_PASSWORD", raising=False)
    with pytest.raises(LeaguepediaError):
        get_credentials()

    monkeypatch.setenv("LEAGUEPEDIA_USERNAME", "User@Bot")
    monkeypatch.setenv("LEAGUEPEDIA_PASSWORD", "token")
    assert get_credentials() == ("User@Bot", "token")
