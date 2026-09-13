-- Un match par ligne : extraction typée des champs match-level depuis le JSONB brut.

with source as (

    select * from {{ source('raw', 'riot_matches') }}

)

select
    match_id,
    region,
    source_puuid,
    source_tier,
    payload -> 'info' ->> 'gameVersion'                                   as game_version,
    split_part(payload -> 'info' ->> 'gameVersion', '.', 1)
        || '.'
        || split_part(payload -> 'info' ->> 'gameVersion', '.', 2)        as patch,
    (payload -> 'info' ->> 'queueId')::int                                as queue_id,
    (payload -> 'info' ->> 'gameDuration')::bigint                        as game_duration_s,
    to_timestamp(((payload -> 'info' ->> 'gameCreation')::bigint) / 1000.0) as game_started_at,
    (payload -> 'info' ->> 'gameEndedInEarlySurrender') is not distinct from 'true'
                                                                          as ended_in_early_surrender,
    loaded_at
from source
