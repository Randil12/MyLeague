from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jobs.datadragon.client import (
    get_champion_detail,
    get_champions,
    get_items,
    get_summoner_spells,
    get_versions,
    write_json,
)


DEFAULT_RAW_DIR = Path("data/bronze/datadragon")
DEFAULT_MINIO_PREFIX = "bronze/datadragon"
LOCALIZED_DATASETS = {
    "champions",
    "champion_details",
    "items",
    "summoner_spells",
}


def build_raw_paths(
    raw_dir: Path,
    dataset: str,
    version: str,
    run_id: str,
    locale: str,
) -> tuple[Path, Path]:
    if dataset in LOCALIZED_DATASETS:
        dataset_path = raw_dir / dataset / f"locale={locale}"
    else:
        dataset_path = raw_dir / dataset

    versioned_path = dataset_path / f"version={version}" / f"{run_id}.json"
    latest_path = dataset_path / "latest.json"
    return versioned_path, latest_path


def build_minio_keys(
    minio_prefix: str,
    dataset: str,
    version: str,
    run_id: str,
    locale: str,
) -> tuple[str, str]:
    if dataset in LOCALIZED_DATASETS:
        dataset_prefix = f"{minio_prefix}/{dataset}/locale={locale}"
    else:
        dataset_prefix = f"{minio_prefix}/{dataset}"

    versioned_key = f"{dataset_prefix}/version={version}/{run_id}.json"
    latest_key = f"{dataset_prefix}/latest.json"
    return versioned_key, latest_key


def save_dataset(
    raw_dir: Path,
    dataset: str,
    version: str,
    run_id: str,
    locale: str,
    payload: Any,
) -> Path:
    versioned_path, latest_path = build_raw_paths(raw_dir, dataset, version, run_id, locale)
    write_json(payload, versioned_path)
    write_json(payload, latest_path)
    return versioned_path


def upload_json_to_minio(
    payload: Any,
    bucket: str,
    key: str,
    endpoint_url: str,
    access_key_id: str,
    secret_access_key: str,
    region_name: str,
) -> None:
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name=region_name,
    )
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"),
        ContentType="application/json",
    )


def extract_data_map(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data", {})
    if not isinstance(data, dict):
        return {}
    return data


def make_champion_details(
    champion_payload: dict[str, Any],
    version: str,
    locale: str,
) -> dict[str, Any]:
    champion_ids = sorted(extract_data_map(champion_payload).keys())
    details = {}
    errors = []

    for champion_id in champion_ids:
        try:
            detail_payload = get_champion_detail(version, champion_id, locale)
            details[champion_id] = detail_payload.get("data", {}).get(champion_id, detail_payload)
        except Exception as exc:  # noqa: BLE001 - keep raw ingestion resilient per champion.
            errors.append({"champion_id": champion_id, "error": str(exc)})

    return {
        "type": "champion_details",
        "version": version,
        "locale": locale,
        "count": len(details),
        "errors": errors,
        "data": details,
    }


def get_minio_config() -> dict[str, str | None]:
    return {
        "endpoint_url": os.getenv("MINIO_ENDPOINT_URL"),
        "bucket": os.getenv("MINIO_BUCKET", "myleague-data"),
        "access_key_id": os.getenv("AWS_ACCESS_KEY_ID"),
        "secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
        "region_name": os.getenv("AWS_DEFAULT_REGION", "eu-west-3"),
    }


def is_minio_enabled(config: dict[str, str | None]) -> bool:
    return all(
        [
            config["endpoint_url"],
            config["bucket"],
            config["access_key_id"],
            config["secret_access_key"],
        ]
    )


def run(
    raw_dir: str | Path = DEFAULT_RAW_DIR,
    locale: str = "fr_FR",
    minio_prefix: str = DEFAULT_MINIO_PREFIX,
) -> dict[str, str]:
    raw_path = Path(raw_dir)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    minio_config = get_minio_config()
    minio_enabled = is_minio_enabled(minio_config)

    versions = get_versions()
    version = versions[0]

    champions = get_champions(version, locale)
    datasets: dict[str, Any] = {
        "versions": versions,
        "champions": champions,
        "champion_details": make_champion_details(champions, version, locale),
        "items": get_items(version, locale),
        "summoner_spells": get_summoner_spells(version, locale),
    }

    outputs: dict[str, str] = {}
    minio_outputs: dict[str, str] = {}

    for dataset, payload in datasets.items():
        outputs[dataset] = str(save_dataset(raw_path, dataset, version, run_id, locale, payload))

        if minio_enabled:
            versioned_key, latest_key = build_minio_keys(
                minio_prefix, dataset, version, run_id, locale
            )
            upload_json_to_minio(
                payload,
                bucket=str(minio_config["bucket"]),
                key=versioned_key,
                endpoint_url=str(minio_config["endpoint_url"]),
                access_key_id=str(minio_config["access_key_id"]),
                secret_access_key=str(minio_config["secret_access_key"]),
                region_name=str(minio_config["region_name"]),
            )
            upload_json_to_minio(
                payload,
                bucket=str(minio_config["bucket"]),
                key=latest_key,
                endpoint_url=str(minio_config["endpoint_url"]),
                access_key_id=str(minio_config["access_key_id"]),
                secret_access_key=str(minio_config["secret_access_key"]),
                region_name=str(minio_config["region_name"]),
            )
            minio_outputs[f"{dataset}_minio"] = f"s3://{minio_config['bucket']}/{versioned_key}"

    result = {
        "version": version,
        "run_id": run_id,
        "locale": locale,
        **outputs,
    }
    if minio_outputs:
        result.update(minio_outputs)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest Riot Data Dragon raw datasets.")
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--locale", default="fr_FR")
    parser.add_argument("--minio-prefix", default=DEFAULT_MINIO_PREFIX)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    result = run(raw_dir=args.raw_dir, locale=args.locale, minio_prefix=args.minio_prefix)
    for key, value in result.items():
        print(f"{key}={value}")
