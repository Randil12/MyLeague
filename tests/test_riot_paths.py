"""Tests unitaires des fonctions de chemins/clés (sans réseau ni BDD)."""

from pathlib import Path

from jobs.datadragon.ingest import build_minio_keys, build_raw_paths
from jobs.riot.euw_ingest import REGION, build_key, build_local_path
from jobs.riot.load_raw import bronze_match_path


def test_bronze_match_path_layout():
    path = bronze_match_path(Path("data/bronze/riot"), "EUW1_123456")
    assert path.as_posix() == (
        f"data/bronze/riot/region={REGION}/matches/match_id=EUW1_123456/match.json"
    )


def test_riot_build_key_is_partitioned_by_region():
    key = build_key("matches", "match_id=EUW1_1/match.json", "bronze/riot")
    assert key == f"bronze/riot/region={REGION}/matches/match_id=EUW1_1/match.json"


def test_riot_build_local_path_mirrors_minio_key():
    path = build_local_path(Path("data/bronze/riot"), "summoners", "puuid=abc/run_id=r1/summoner.json")
    assert path.as_posix() == (
        f"data/bronze/riot/region={REGION}/summoners/puuid=abc/run_id=r1/summoner.json"
    )


def test_datadragon_localized_dataset_paths_include_locale():
    versioned, latest = build_raw_paths(
        Path("data/bronze/datadragon"), "champions", "16.13.1", "run1", "fr_FR"
    )
    assert "locale=fr_FR" in versioned.as_posix()
    assert versioned.as_posix().endswith("version=16.13.1/run1.json")
    assert latest.as_posix().endswith("locale=fr_FR/latest.json")


def test_datadragon_minio_keys_match_local_layout():
    versioned_key, latest_key = build_minio_keys(
        "bronze/datadragon", "versions", "16.13.1", "run1", "fr_FR"
    )
    assert versioned_key == "bronze/datadragon/versions/version=16.13.1/run1.json"
    assert latest_key == "bronze/datadragon/versions/latest.json"
