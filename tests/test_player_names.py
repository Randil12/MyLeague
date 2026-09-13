from backend import queries


def test_player_labels_do_not_fall_back_to_technical_ids():
    assert "gold.gold_player_names" in queries.PLAYERS
    assert "n.riot_id" in queries.PLAYERS
    assert "Pseudo indisponible" in queries.PLAYERS
    assert "left(puuid" not in queries.PLAYERS.lower()
    # Internal selection and SQL relationships still use the immutable identifier.
    assert "SELECT t.puuid" in queries.PLAYERS
