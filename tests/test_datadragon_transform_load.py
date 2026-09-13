"""Tests unitaires de la partie Transform de l'ETL Data Dragon (sans réseau ni BDD)."""

from jobs.datadragon.transform_load import (
    to_int,
    to_num,
    transform_champions,
    transform_items,
    transform_runes,
    transform_summoner_spells,
)

CHAMPIONS_PAYLOAD = {
    "version": "16.13.1",
    "data": {
        "Aatrox": {
            "key": "266",
            "name": "Aatrox",
            "title": "Épée des Darkin",
            "tags": ["Fighter", "Tank"],
            "partype": "Puits de sang",
            "info": {"attack": 8, "defense": 4, "magic": 3, "difficulty": 4},
            "stats": {
                "hp": 650,
                "armor": 38,
                "attackdamage": 60,
                "attackrange": 175,
                "movespeed": 345,
            },
        }
    },
}

ITEMS_PAYLOAD = {
    "version": "16.13.1",
    "data": {
        "1001": {
            "name": "Bottes",
            "plaintext": "Améliore la vitesse de déplacement",
            "gold": {"base": 300, "total": 300, "sell": 210, "purchasable": True},
            "tags": ["Boots"],
            "stats": {"FlatMovementSpeedMod": 25},
        }
    },
}

SPELLS_PAYLOAD = {
    "version": "16.13.1",
    "data": {
        "SummonerFlash": {
            "key": "4",
            "name": "Saut éclair",
            "description": "Téléporte le champion.",
            "cooldown": [300.0],
            "summonerLevel": 7,
            "modes": ["CLASSIC", "ARAM"],
        }
    },
}


def test_transform_champions_extracts_typed_row():
    version, rows = transform_champions(CHAMPIONS_PAYLOAD, "fr_FR")
    assert version == "16.13.1"
    assert len(rows) == 1

    row = rows[0]
    assert row["champion_id"] == "Aatrox"
    assert row["champion_key"] == 266
    assert row["primary_role"] == "Fighter"
    assert row["difficulty"] == 4
    assert row["hp"] == 650.0
    assert row["locale"] == "fr_FR"


def test_transform_items_flattens_gold():
    version, rows = transform_items(ITEMS_PAYLOAD, "fr_FR")
    assert version == "16.13.1"

    row = rows[0]
    assert row["item_id"] == 1001
    assert row["name"] == "Bottes"
    assert row["gold_total"] == 300
    assert row["purchasable"] is True
    assert row["tags"] == ["Boots"]


def test_transform_summoner_spells_takes_first_cooldown():
    version, rows = transform_summoner_spells(SPELLS_PAYLOAD, "fr_FR")
    assert version == "16.13.1"

    row = rows[0]
    assert row["spell_id"] == "SummonerFlash"
    assert row["spell_key"] == 4
    assert row["cooldown"] == 300.0
    assert row["summoner_level"] == 7


def test_to_int_and_to_num_handle_bad_values():
    assert to_int("42") == 42
    assert to_int("abc") is None
    assert to_int(None) is None
    assert to_num("1.5") == 1.5
    assert to_num(None) is None


def test_transform_handles_empty_payload():
    version, rows = transform_champions({"version": "x", "data": {}}, "fr_FR")
    assert version == "x"
    assert rows == []


RUNES_PAYLOAD = {
    "version": "16.13.1",
    "locale": "fr_FR",
    "data": [
        {
            "id": 8100,
            "key": "Domination",
            "name": "Domination",
            "slots": [
                {
                    "runes": [
                        {"id": 8112, "key": "Electrocute", "name": "Électrocution"},
                        {"id": 8128, "key": "DarkHarvest", "name": "Moisson noire"},
                    ]
                },
                {
                    "runes": [
                        {"id": 8126, "key": "CheapShot", "name": "Coup bas"},
                    ]
                },
            ],
        }
    ],
}


def test_transform_runes_flattens_styles_and_flags_keystones():
    version, rows = transform_runes(RUNES_PAYLOAD, "fr_FR")
    assert version == "16.13.1"
    assert len(rows) == 3

    keystones = [r for r in rows if r["is_keystone"]]
    assert {r["rune_id"] for r in keystones} == {8112, 8128}

    cheap_shot = next(r for r in rows if r["rune_id"] == 8126)
    assert cheap_shot["is_keystone"] is False
    assert cheap_shot["slot_index"] == 1
    assert cheap_shot["style_name"] == "Domination"
