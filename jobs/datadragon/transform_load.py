"""ETL Data Dragon : Extract (bronze) -> Transform (Python) -> Load (Postgres reference).

Pattern ETL assumé (vs ELT Riot) : référentiel de faible volume, schéma stable,
transformations connues à l'avance (typage, aplatissement, extraction de colonnes).
La transformation est faite en Python AVANT le chargement dans le warehouse.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

DEFAULT_RAW_DIR = Path("data/bronze/datadragon")
DEFAULT_MINIO_PREFIX = "bronze/datadragon"
LOCALIZED_DATASETS = {"champions", "items", "summoner_spells", "runes"}


def get_gold_conn():
    import psycopg2

    return psycopg2.connect(
        host=os.getenv("GOLD_POSTGRES_HOST", "gold-postgres"),
        port=int(os.getenv("GOLD_POSTGRES_PORT", "5432")),
        dbname=os.getenv("GOLD_POSTGRES_DB", "gold"),
        user=os.getenv("GOLD_POSTGRES_USER", "gold"),
        password=os.getenv("GOLD_POSTGRES_PASSWORD", "gold"),
    )


def init_reference_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS reference")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS reference.dim_champion (
                version TEXT NOT NULL,
                locale TEXT NOT NULL,
                champion_id TEXT NOT NULL,
                champion_key INTEGER NOT NULL,
                name TEXT NOT NULL,
                title TEXT,
                primary_role TEXT,
                tags TEXT[],
                partype TEXT,
                attack INTEGER,
                defense INTEGER,
                magic INTEGER,
                difficulty INTEGER,
                hp NUMERIC,
                armor NUMERIC,
                attack_damage NUMERIC,
                attack_range NUMERIC,
                move_speed NUMERIC,
                stats JSONB,
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (version, locale, champion_id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS reference.dim_item (
                version TEXT NOT NULL,
                locale TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                plaintext TEXT,
                gold_base INTEGER,
                gold_total INTEGER,
                gold_sell INTEGER,
                purchasable BOOLEAN,
                tags TEXT[],
                stats JSONB,
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (version, locale, item_id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS reference.dim_rune (
                version TEXT NOT NULL,
                locale TEXT NOT NULL,
                rune_id INTEGER NOT NULL,
                rune_key TEXT,
                rune_name TEXT NOT NULL,
                style_id INTEGER,
                style_key TEXT,
                style_name TEXT,
                slot_index INTEGER,
                is_keystone BOOLEAN NOT NULL DEFAULT FALSE,
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (version, locale, rune_id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS reference.dim_summoner_spell (
                version TEXT NOT NULL,
                locale TEXT NOT NULL,
                spell_id TEXT NOT NULL,
                spell_key INTEGER,
                name TEXT NOT NULL,
                description TEXT,
                cooldown NUMERIC,
                summoner_level INTEGER,
                modes TEXT[],
                loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (version, locale, spell_id)
            )
            """
        )
    conn.commit()


def read_latest(
    raw_dir: Path,
    dataset: str,
    locale: str,
    minio_prefix: str = DEFAULT_MINIO_PREFIX,
) -> dict[str, Any]:
    """Extract : lit le pointeur latest du dataset depuis la zone bronze.

    MinIO est l'unique zone bronze en fonctionnement nominal ; la copie locale
    n'existe qu'en mode dégradé (exécution sans MinIO).
    """
    if dataset in LOCALIZED_DATASETS:
        local_path = raw_dir / dataset / f"locale={locale}" / "latest.json"
        minio_key = f"{minio_prefix}/{dataset}/locale={locale}/latest.json"
    else:
        local_path = raw_dir / dataset / "latest.json"
        minio_key = f"{minio_prefix}/{dataset}/latest.json"

    from jobs.riot.euw_ingest import get_minio_config, is_minio_enabled

    minio_config = get_minio_config()
    if is_minio_enabled(minio_config):
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=minio_config["endpoint_url"],
            aws_access_key_id=minio_config["access_key_id"],
            aws_secret_access_key=minio_config["secret_access_key"],
            region_name=minio_config["region_name"],
        )
        try:
            obj = client.get_object(Bucket=str(minio_config["bucket"]), Key=minio_key)
        except client.exceptions.NoSuchKey as exc:
            # Uniformise avec le mode local : dataset absent = FileNotFoundError
            # (les datasets optionnels comme les runes sont ignorés proprement).
            raise FileNotFoundError(
                f"Bronze object missing for dataset '{dataset}': s3://"
                f"{minio_config['bucket']}/{minio_key}"
            ) from exc
        return json.loads(obj["Body"].read().decode("utf-8"))

    if not local_path.exists():
        raise FileNotFoundError(f"Bronze file missing for dataset '{dataset}': {local_path}")
    return json.loads(local_path.read_text(encoding="utf-8"))


def to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def transform_champions(payload: dict[str, Any], locale: str) -> tuple[str, list[dict[str, Any]]]:
    version = payload.get("version", "unknown")
    rows = []
    for champion_id, champ in sorted(payload.get("data", {}).items()):
        info = champ.get("info", {})
        stats = champ.get("stats", {})
        tags = champ.get("tags", []) or []
        rows.append(
            {
                "version": version,
                "locale": locale,
                "champion_id": champion_id,
                "champion_key": to_int(champ.get("key")),
                "name": champ.get("name"),
                "title": champ.get("title"),
                "primary_role": tags[0] if tags else None,
                "tags": tags,
                "partype": champ.get("partype"),
                "attack": to_int(info.get("attack")),
                "defense": to_int(info.get("defense")),
                "magic": to_int(info.get("magic")),
                "difficulty": to_int(info.get("difficulty")),
                "hp": to_num(stats.get("hp")),
                "armor": to_num(stats.get("armor")),
                "attack_damage": to_num(stats.get("attackdamage")),
                "attack_range": to_num(stats.get("attackrange")),
                "move_speed": to_num(stats.get("movespeed")),
                "stats": stats,
            }
        )
    return version, rows


def transform_items(payload: dict[str, Any], locale: str) -> tuple[str, list[dict[str, Any]]]:
    version = payload.get("version", "unknown")
    rows = []
    for item_id, item in sorted(payload.get("data", {}).items()):
        gold = item.get("gold", {})
        rows.append(
            {
                "version": version,
                "locale": locale,
                "item_id": to_int(item_id),
                "name": item.get("name"),
                "plaintext": item.get("plaintext"),
                "gold_base": to_int(gold.get("base")),
                "gold_total": to_int(gold.get("total")),
                "gold_sell": to_int(gold.get("sell")),
                "purchasable": gold.get("purchasable"),
                "tags": item.get("tags", []) or [],
                "stats": item.get("stats", {}),
            }
        )
    return version, rows


def transform_summoner_spells(payload: dict[str, Any], locale: str) -> tuple[str, list[dict[str, Any]]]:
    version = payload.get("version", "unknown")
    rows = []
    for spell_id, spell in sorted(payload.get("data", {}).items()):
        cooldowns = spell.get("cooldown") or []
        rows.append(
            {
                "version": version,
                "locale": locale,
                "spell_id": spell_id,
                "spell_key": to_int(spell.get("key")),
                "name": spell.get("name"),
                "description": spell.get("description"),
                "cooldown": to_num(cooldowns[0]) if cooldowns else None,
                "summoner_level": to_int(spell.get("summonerLevel")),
                "modes": spell.get("modes", []) or [],
            }
        )
    return version, rows


def transform_runes(payload: dict[str, Any], locale: str) -> tuple[str, list[dict[str, Any]]]:
    """Aplatit runesReforged : styles -> slots -> runes (slot 0 = keystones)."""
    version = payload.get("version", "unknown")
    rows = []
    for style in payload.get("data", []) or []:
        style_id = to_int(style.get("id"))
        style_key = style.get("key")
        style_name = style.get("name")
        for slot_index, slot in enumerate(style.get("slots", []) or []):
            for rune in slot.get("runes", []) or []:
                rows.append(
                    {
                        "version": version,
                        "locale": locale,
                        "rune_id": to_int(rune.get("id")),
                        "rune_key": rune.get("key"),
                        "rune_name": rune.get("name"),
                        "style_id": style_id,
                        "style_key": style_key,
                        "style_name": style_name,
                        "slot_index": slot_index,
                        "is_keystone": slot_index == 0,
                    }
                )
    return version, rows


def load_champions(conn, rows: list[dict[str, Any]]) -> int:
    from psycopg2.extras import Json

    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO reference.dim_champion (
                    version, locale, champion_id, champion_key, name, title,
                    primary_role, tags, partype, attack, defense, magic, difficulty,
                    hp, armor, attack_damage, attack_range, move_speed, stats, loaded_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (version, locale, champion_id) DO UPDATE SET
                    champion_key = EXCLUDED.champion_key,
                    name = EXCLUDED.name,
                    title = EXCLUDED.title,
                    primary_role = EXCLUDED.primary_role,
                    tags = EXCLUDED.tags,
                    partype = EXCLUDED.partype,
                    attack = EXCLUDED.attack,
                    defense = EXCLUDED.defense,
                    magic = EXCLUDED.magic,
                    difficulty = EXCLUDED.difficulty,
                    hp = EXCLUDED.hp,
                    armor = EXCLUDED.armor,
                    attack_damage = EXCLUDED.attack_damage,
                    attack_range = EXCLUDED.attack_range,
                    move_speed = EXCLUDED.move_speed,
                    stats = EXCLUDED.stats,
                    loaded_at = NOW()
                """,
                (
                    row["version"], row["locale"], row["champion_id"], row["champion_key"],
                    row["name"], row["title"], row["primary_role"], row["tags"],
                    row["partype"], row["attack"], row["defense"], row["magic"],
                    row["difficulty"], row["hp"], row["armor"], row["attack_damage"],
                    row["attack_range"], row["move_speed"], Json(row["stats"]),
                ),
            )
    conn.commit()
    return len(rows)


def load_items(conn, rows: list[dict[str, Any]]) -> int:
    from psycopg2.extras import Json

    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO reference.dim_item (
                    version, locale, item_id, name, plaintext,
                    gold_base, gold_total, gold_sell, purchasable, tags, stats, loaded_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (version, locale, item_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    plaintext = EXCLUDED.plaintext,
                    gold_base = EXCLUDED.gold_base,
                    gold_total = EXCLUDED.gold_total,
                    gold_sell = EXCLUDED.gold_sell,
                    purchasable = EXCLUDED.purchasable,
                    tags = EXCLUDED.tags,
                    stats = EXCLUDED.stats,
                    loaded_at = NOW()
                """,
                (
                    row["version"], row["locale"], row["item_id"], row["name"],
                    row["plaintext"], row["gold_base"], row["gold_total"],
                    row["gold_sell"], row["purchasable"], row["tags"], Json(row["stats"]),
                ),
            )
    conn.commit()
    return len(rows)


def load_summoner_spells(conn, rows: list[dict[str, Any]]) -> int:
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO reference.dim_summoner_spell (
                    version, locale, spell_id, spell_key, name,
                    description, cooldown, summoner_level, modes, loaded_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (version, locale, spell_id) DO UPDATE SET
                    spell_key = EXCLUDED.spell_key,
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    cooldown = EXCLUDED.cooldown,
                    summoner_level = EXCLUDED.summoner_level,
                    modes = EXCLUDED.modes,
                    loaded_at = NOW()
                """,
                (
                    row["version"], row["locale"], row["spell_id"], row["spell_key"],
                    row["name"], row["description"], row["cooldown"],
                    row["summoner_level"], row["modes"],
                ),
            )
    conn.commit()
    return len(rows)


def load_runes(conn, rows: list[dict[str, Any]]) -> int:
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO reference.dim_rune (
                    version, locale, rune_id, rune_key, rune_name,
                    style_id, style_key, style_name, slot_index, is_keystone, loaded_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (version, locale, rune_id) DO UPDATE SET
                    rune_key = EXCLUDED.rune_key,
                    rune_name = EXCLUDED.rune_name,
                    style_id = EXCLUDED.style_id,
                    style_key = EXCLUDED.style_key,
                    style_name = EXCLUDED.style_name,
                    slot_index = EXCLUDED.slot_index,
                    is_keystone = EXCLUDED.is_keystone,
                    loaded_at = NOW()
                """,
                (
                    row["version"], row["locale"], row["rune_id"], row["rune_key"],
                    row["rune_name"], row["style_id"], row["style_key"],
                    row["style_name"], row["slot_index"], row["is_keystone"],
                ),
            )
    conn.commit()
    return len(rows)


def run(raw_dir: str | Path = DEFAULT_RAW_DIR, locale: str = "fr_FR") -> dict[str, Any]:
    raw_path = Path(raw_dir)

    # Extract (depuis la zone bronze, copie brute conservée pour la traçabilité)
    champions_payload = read_latest(raw_path, "champions", locale)
    items_payload = read_latest(raw_path, "items", locale)
    spells_payload = read_latest(raw_path, "summoner_spells", locale)

    # Transform (typage, aplatissement, extraction de colonnes analytiques)
    version, champion_rows = transform_champions(champions_payload, locale)
    _, item_rows = transform_items(items_payload, locale)
    _, spell_rows = transform_summoner_spells(spells_payload, locale)

    # Runes : dataset ajouté après la première ingestion — absent des anciens bronze.
    rune_rows: list[dict[str, Any]] = []
    try:
        runes_payload = read_latest(raw_path, "runes", locale)
        _, rune_rows = transform_runes(runes_payload, locale)
    except FileNotFoundError:
        pass

    # Load (upsert idempotent dans le schéma reference)
    conn = get_gold_conn()
    try:
        init_reference_schema(conn)
        champions_loaded = load_champions(conn, champion_rows)
        items_loaded = load_items(conn, item_rows)
        spells_loaded = load_summoner_spells(conn, spell_rows)
        runes_loaded = load_runes(conn, rune_rows)
    finally:
        conn.close()

    return {
        "version": version,
        "locale": locale,
        "champions_loaded": champions_loaded,
        "items_loaded": items_loaded,
        "summoner_spells_loaded": spells_loaded,
        "runes_loaded": runes_loaded,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ETL Data Dragon: transform bronze JSON and load Postgres reference tables."
    )
    parser.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    parser.add_argument("--locale", default="fr_FR")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    result = run(raw_dir=args.raw_dir, locale=args.locale)
    for key, value in result.items():
        print(f"{key}={value}")
