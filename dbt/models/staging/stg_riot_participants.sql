-- Un participant par ligne (10 par match) : aplatissement du tableau info.participants.

with source as (

    select * from {{ source('raw', 'riot_matches') }}

)

select
    s.match_id,
    p.value ->> 'puuid'                                   as puuid,
    (p.value ->> 'championId')::int                       as champion_key,
    p.value ->> 'championName'                            as champion_name,
    (p.value ->> 'teamId')::int                           as team_id,
    nullif(p.value ->> 'teamPosition', '')                as team_position,
    (p.value ->> 'win')::boolean                          as win,
    (p.value ->> 'kills')::int                            as kills,
    (p.value ->> 'deaths')::int                           as deaths,
    (p.value ->> 'assists')::int                          as assists,
    (p.value ->> 'goldEarned')::int                       as gold_earned,
    (p.value ->> 'totalMinionsKilled')::int
        + coalesce((p.value ->> 'neutralMinionsKilled')::int, 0)
                                                          as total_cs,
    (p.value ->> 'visionScore')::int                      as vision_score,
    (p.value ->> 'totalDamageDealtToChampions')::bigint   as damage_to_champions,
    (p.value ->> 'summoner1Id')::int                      as summoner_spell_1,
    (p.value ->> 'summoner2Id')::int                      as summoner_spell_2,
    (p.value ->> 'item0')::int                            as item0,
    (p.value ->> 'item1')::int                            as item1,
    (p.value ->> 'item2')::int                            as item2,
    (p.value ->> 'item3')::int                            as item3,
    (p.value ->> 'item4')::int                            as item4,
    (p.value ->> 'item5')::int                            as item5,
    (p.value ->> 'item6')::int                            as trinket,
    (p.value -> 'perks' -> 'styles' -> 0 -> 'selections' -> 0 ->> 'perk')::int
                                                          as keystone_id,
    (p.value -> 'perks' -> 'styles' -> 0 ->> 'style')::int as primary_style_id,
    (p.value -> 'perks' -> 'styles' -> 1 ->> 'style')::int as sub_style_id
from source as s
cross join lateral jsonb_array_elements(s.payload -> 'info' -> 'participants') as p (value)
