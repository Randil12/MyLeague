CREATE SCHEMA IF NOT EXISTS raw;        -- ELT : JSON bruts (Riot) chargés tels quels, transformés par dbt
CREATE SCHEMA IF NOT EXISTS reference;  -- ETL : référentiel Data Dragon transformé en Python avant chargement
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS intermediate;
CREATE SCHEMA IF NOT EXISTS gold;
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE IF NOT EXISTS raw.riot_matches (
    match_id TEXT PRIMARY KEY,
    region TEXT NOT NULL,
    game_version TEXT,
    source_puuid TEXT,
    source_tier TEXT,
    payload JSONB NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE raw.riot_matches ADD COLUMN IF NOT EXISTS source_puuid TEXT;
ALTER TABLE raw.riot_matches ADD COLUMN IF NOT EXISTS source_tier TEXT;

CREATE INDEX IF NOT EXISTS idx_raw_riot_matches_game_version
    ON raw.riot_matches (game_version);

CREATE TABLE IF NOT EXISTS raw.riot_match_timelines (
    match_id TEXT PRIMARY KEY,
    region TEXT NOT NULL,
    payload JSONB NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raw.riot_live_game_snapshots (
    game_id BIGINT PRIMARY KEY,
    region TEXT NOT NULL,
    queue_id INTEGER,
    observed_puuid TEXT,
    game_started_at TIMESTAMPTZ,
    payload JSONB NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raw.leaguepedia_tournaments (
    overview_page TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raw.leaguepedia_teams (
    overview_page TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raw.leaguepedia_players (
    overview_page TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raw.leaguepedia_scoreboard_games (
    game_id TEXT PRIMARY KEY,
    patch TEXT,
    game_date TIMESTAMPTZ,
    payload JSONB NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lp_scoreboard_games_patch
    ON raw.leaguepedia_scoreboard_games (patch);

CREATE TABLE IF NOT EXISTS raw.leaguepedia_scoreboard_players (
    game_id TEXT NOT NULL,
    player_page TEXT NOT NULL,
    champion TEXT,
    role TEXT,
    game_date TIMESTAMPTZ,
    payload JSONB NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (game_id, player_page)
);

CREATE TABLE IF NOT EXISTS raw.riot_patch_notes (
    patch TEXT PRIMARY KEY,
    locale TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    section_count INTEGER,
    payload JSONB NOT NULL,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raw.riot_champion_masteries (
    region TEXT NOT NULL,
    puuid TEXT NOT NULL,
    champion_key INTEGER NOT NULL,
    mastery_level INTEGER,
    mastery_points BIGINT,
    last_played_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (puuid, champion_key)
);

CREATE TABLE IF NOT EXISTS audit.pipeline_runs (
    run_id TEXT PRIMARY KEY,
    pipeline_name TEXT NOT NULL,
    source TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    records_read INTEGER DEFAULT 0,
    records_written INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit.riot_tracked_players (
    region TEXT NOT NULL,
    puuid TEXT PRIMARY KEY,
    summoner_id TEXT,
    account_id TEXT,
    profile_icon_id INTEGER,
    summoner_level BIGINT,
    riot_summoner_name TEXT,
    tier TEXT,
    rank TEXT,
    league_points INTEGER,
    wins INTEGER,
    losses INTEGER,
    queue_type TEXT,
    first_seen_master_plus_at TIMESTAMPTZ NOT NULL,
    last_seen_master_plus_at TIMESTAMPTZ NOT NULL,
    last_match_ingestion_at TIMESTAMPTZ,
    is_currently_master_plus BOOLEAN NOT NULL DEFAULT TRUE,
    is_tracked BOOLEAN NOT NULL DEFAULT TRUE,
    tracking_source TEXT NOT NULL DEFAULT 'ladder',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit.riot_match_ingestion (
    region TEXT NOT NULL,
    match_id TEXT PRIMARY KEY,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    loaded_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'pending',
    source_puuid TEXT,
    run_id TEXT,
    bronze_uri TEXT,
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    timeline_status TEXT,
    timeline_uri TEXT,
    timeline_retry_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit.pipeline_alerts (
    pipeline_name TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    first_detected_at TIMESTAMPTZ NOT NULL,
    last_detected_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    notification_sent BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (pipeline_name, alert_type)
);

CREATE INDEX IF NOT EXISTS idx_riot_tracked_players_region_tracked
    ON audit.riot_tracked_players (region, is_tracked, last_seen_master_plus_at DESC);

CREATE INDEX IF NOT EXISTS idx_riot_tracked_players_match_cursor
    ON audit.riot_tracked_players (region, is_tracked, last_match_ingestion_at);

CREATE INDEX IF NOT EXISTS idx_riot_match_ingestion_status_retry
    ON audit.riot_match_ingestion (region, status, retry_count, updated_at);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_pipeline_started
    ON audit.pipeline_runs (pipeline_name, started_at DESC);

-- Les tables de référence doivent exister avant la création des vues *_latest.
-- Elles sont aussi créées par le job Data Dragon pour garder le job autonome,
-- mais l'initialisation du warehouse doit fonctionner sur une base vide.
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
);

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
);

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
);

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
);

-- Dimensions "latest" du modèle en étoile : dernière version connue de chaque
-- entité du référentiel, avec une clé simple — jointes à gold.fact_match_participant
-- (champion_key, item, rune, sort) pour les analyses ad hoc.
CREATE OR REPLACE VIEW reference.dim_champion_latest AS
SELECT DISTINCT ON (champion_key)
    champion_key, champion_id, name, title, primary_role, tags, version, locale
FROM reference.dim_champion
ORDER BY champion_key, loaded_at DESC;

CREATE OR REPLACE VIEW reference.dim_item_latest AS
SELECT DISTINCT ON (item_id)
    item_id, name, plaintext, gold_total, purchasable, tags, version, locale
FROM reference.dim_item
ORDER BY item_id, loaded_at DESC;

CREATE OR REPLACE VIEW reference.dim_rune_latest AS
SELECT DISTINCT ON (rune_id)
    rune_id, rune_key, rune_name, style_id, style_name, is_keystone, version, locale
FROM reference.dim_rune
ORDER BY rune_id, loaded_at DESC;

CREATE OR REPLACE VIEW reference.dim_summoner_spell_latest AS
SELECT DISTINCT ON (spell_key)
    spell_key, spell_id, name, description, cooldown, version, locale
FROM reference.dim_summoner_spell
ORDER BY spell_key, loaded_at DESC;

-- Vue de supervision : expose les volumes de la zone raw sans en ouvrir l'accès.
-- Une vue s'exécute avec les droits de son propriétaire (gold) : data_analyst
-- peut lire les compteurs sans aucun droit sur le schéma raw lui-même.
CREATE OR REPLACE VIEW audit.v_raw_row_counts AS
SELECT 'riot_matches'::text AS table_name, count(*)::bigint AS row_count FROM raw.riot_matches
UNION ALL SELECT 'riot_match_timelines', count(*) FROM raw.riot_match_timelines
UNION ALL SELECT 'riot_live_game_snapshots', count(*) FROM raw.riot_live_game_snapshots
UNION ALL SELECT 'leaguepedia_scoreboard_games', count(*) FROM raw.leaguepedia_scoreboard_games
UNION ALL SELECT 'riot_patch_notes', count(*) FROM raw.riot_patch_notes;

-- ============================================================
-- Clés étrangères sur les zones stables (raw, audit).
-- NOT VALID : appliquées aux nouvelles lignes sans bloquer le démarrage
-- si des lignes historiques sont orphelines (VALIDATE CONSTRAINT possible ensuite).
-- Volontairement absentes de staging/intermediate/gold (reconstruits par dbt
-- à chaque run — l'intégrité y est vérifiée par les tests dbt 'relationships')
-- et des dimensions reference (jointure versionnée par patch, inexprimable en FK).
-- ============================================================
-- Nettoyage des anciens noms de contraintes utilisés par les premières versions.
ALTER TABLE raw.riot_match_timelines DROP CONSTRAINT IF EXISTS fk_timelines_match;
ALTER TABLE raw.riot_matches DROP CONSTRAINT IF EXISTS fk_matches_source_player;
ALTER TABLE raw.riot_champion_masteries DROP CONSTRAINT IF EXISTS fk_masteries_player;
ALTER TABLE audit.riot_match_ingestion DROP CONSTRAINT IF EXISTS fk_match_ingestion_player;

ALTER TABLE raw.riot_match_timelines DROP CONSTRAINT IF EXISTS fk_timeline_match;
ALTER TABLE raw.riot_match_timelines
    ADD CONSTRAINT fk_timeline_match FOREIGN KEY (match_id)
    REFERENCES raw.riot_matches (match_id) ON DELETE CASCADE NOT VALID;

ALTER TABLE raw.riot_matches DROP CONSTRAINT IF EXISTS fk_match_source_player;
ALTER TABLE raw.riot_matches
    ADD CONSTRAINT fk_match_source_player FOREIGN KEY (source_puuid)
    REFERENCES audit.riot_tracked_players (puuid) ON DELETE SET NULL NOT VALID;

ALTER TABLE raw.riot_champion_masteries DROP CONSTRAINT IF EXISTS fk_mastery_player;
ALTER TABLE raw.riot_champion_masteries
    ADD CONSTRAINT fk_mastery_player FOREIGN KEY (puuid)
    REFERENCES audit.riot_tracked_players (puuid) ON DELETE CASCADE NOT VALID;

ALTER TABLE raw.riot_live_game_snapshots DROP CONSTRAINT IF EXISTS fk_live_game_player;
ALTER TABLE raw.riot_live_game_snapshots
    ADD CONSTRAINT fk_live_game_player FOREIGN KEY (observed_puuid)
    REFERENCES audit.riot_tracked_players (puuid) ON DELETE SET NULL NOT VALID;

ALTER TABLE audit.riot_match_ingestion DROP CONSTRAINT IF EXISTS fk_ingestion_source_player;
ALTER TABLE audit.riot_match_ingestion
    ADD CONSTRAINT fk_ingestion_source_player FOREIGN KEY (source_puuid)
    REFERENCES audit.riot_tracked_players (puuid) ON DELETE SET NULL NOT VALID;

ALTER TABLE raw.leaguepedia_scoreboard_players DROP CONSTRAINT IF EXISTS fk_lp_players_game;
ALTER TABLE raw.leaguepedia_scoreboard_players
    ADD CONSTRAINT fk_lp_players_game FOREIGN KEY (game_id)
    REFERENCES raw.leaguepedia_scoreboard_games (game_id) ON DELETE CASCADE NOT VALID;
