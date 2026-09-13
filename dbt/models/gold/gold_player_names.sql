-- Latest known identity from collected matches; no extra Riot API calls.
-- Keep PUUID as join key, never as the displayed name.
with identities as (
    select
        p.value ->> 'puuid' as puuid,
        nullif(btrim(p.value ->> 'riotIdGameName'), '') as game_name,
        nullif(btrim(p.value ->> 'riotIdTagline'), '') as tag_line,
        nullif(btrim(p.value ->> 'summonerName'), '') as legacy_name,
        m.game_started_at,
        r.loaded_at,
        r.match_id
    from {{ source('raw', 'riot_matches') }} r
    join {{ ref('stg_riot_matches') }} m using (match_id)
    cross join lateral jsonb_array_elements(r.payload -> 'info' -> 'participants') p(value)
), named as (
    select *,
        case when game_name is not null and tag_line is not null
            then game_name || '#' || tag_line end as riot_id,
        coalesce(game_name, legacy_name) as display_name
    from identities
    where nullif(puuid, '') is not null
)
select distinct on (puuid)
    puuid, riot_id, display_name, game_started_at as name_observed_at
from named
where display_name is not null and display_name <> puuid
order by puuid, game_started_at desc nulls last, loaded_at desc, match_id desc
