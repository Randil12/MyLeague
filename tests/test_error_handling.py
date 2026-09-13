"""Tests unitaires des garde-fous d'ingestion (sans réseau ni BDD)."""

from jobs.riot.load_raw import parse_s3_uri, validate_match_payload


def make_valid_payload(match_id="EUW1_123"):
    return {
        "metadata": {"matchId": match_id},
        "info": {
            "gameVersion": "16.13.695.9999",
            "participants": [{"puuid": f"p{i}"} for i in range(10)],
        },
    }


def test_valid_payload_passes():
    assert validate_match_payload("EUW1_123", make_valid_payload()) is None


def test_rejects_non_dict_payload():
    assert validate_match_payload("EUW1_123", None) is not None
    assert validate_match_payload("EUW1_123", []) is not None
    assert validate_match_payload("EUW1_123", "corrompu") is not None


def test_rejects_match_id_mismatch():
    payload = make_valid_payload("EUW1_999")
    reason = validate_match_payload("EUW1_123", payload)
    assert reason is not None and "mismatch" in reason


def test_rejects_wrong_participant_count():
    payload = make_valid_payload()
    payload["info"]["participants"] = payload["info"]["participants"][:7]
    reason = validate_match_payload("EUW1_123", payload)
    assert reason is not None and "participants" in reason


def test_rejects_missing_info_or_version():
    assert validate_match_payload("EUW1_123", {"metadata": {}}) is not None
    payload = make_valid_payload()
    payload["info"]["gameVersion"] = ""
    assert validate_match_payload("EUW1_123", payload) is not None


def test_parse_s3_uri():
    assert parse_s3_uri("s3://bucket/path/to/key.json") == ("bucket", "path/to/key.json")
    assert parse_s3_uri("s3://bucket") is None
    assert parse_s3_uri("/local/path.json") is None
    assert parse_s3_uri(None) is None
