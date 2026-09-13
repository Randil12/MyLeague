"""Tests unitaires des nouvelles sources Riot (sans réseau ni BDD)."""

import pytest

from jobs.riot.academy import parse_riot_id
from jobs.riot.euw_ingest import parse_extra_tiers


def test_parse_riot_id_valid():
    assert parse_riot_id("Faker#KR1") == ("Faker", "KR1")
    assert parse_riot_id("  Nexus Player #EUW ") == ("Nexus Player", "EUW")


@pytest.mark.parametrize("bad_id", ["Faker", "#EUW", "Faker#", "", "#"])
def test_parse_riot_id_invalid(bad_id):
    with pytest.raises(ValueError):
        parse_riot_id(bad_id)


def test_parse_extra_tiers_full_spec():
    assert parse_extra_tiers("DIAMOND:I:2,EMERALD:II:1") == [
        ("DIAMOND", "I", 2),
        ("EMERALD", "II", 1),
    ]


def test_parse_extra_tiers_defaults_and_empty():
    assert parse_extra_tiers("diamond") == [("DIAMOND", "I", 1)]
    assert parse_extra_tiers("") == []
    assert parse_extra_tiers(None) == []
    assert parse_extra_tiers(" GOLD:IV , ") == [("GOLD", "IV", 1)]
