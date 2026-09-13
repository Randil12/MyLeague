-- Un ban par ligne (jusqu'à 10 par match). championId = -1 signifie "pas de ban".

with source as (

    select * from {{ source('raw', 'riot_matches') }}

)

select
    s.match_id,
    (t.value ->> 'teamId')::int      as team_id,
    (b.value ->> 'championId')::int  as champion_key,
    (b.value ->> 'pickTurn')::int    as pick_turn
from source as s
cross join lateral jsonb_array_elements(s.payload -> 'info' -> 'teams') as t (value)
cross join lateral jsonb_array_elements(t.value -> 'bans') as b (value)
where (b.value ->> 'championId')::int > 0
