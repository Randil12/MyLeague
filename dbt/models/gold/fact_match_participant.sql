-- Table de faits du modèle en étoile : un participant par ligne (grain le plus fin).
-- C'est la matérialisation physique du modèle dimensionnel : les agrégats gold
-- (méta, builds, keystones) en sont des vues résumées ; les analyses ad hoc
-- des coachs partent d'ici, jointes aux dimensions reference.dim_*_latest.

select
    match_id || '|' || puuid as fact_participant_key,
    match_id,
    puuid,
    champion_key,
    champion_name,
    team_id,
    team_position,
    win,
    kills,
    deaths,
    assists,
    gold_earned,
    total_cs,
    vision_score,
    damage_to_champions,
    summoner_spell_1,
    summoner_spell_2,
    item0, item1, item2, item3, item4, item5,
    trinket,
    keystone_id,
    primary_style_id,
    sub_style_id,
    patch,
    game_version,
    game_duration_s,
    game_started_at,
    source_tier
from {{ ref('int_match_participants') }}
