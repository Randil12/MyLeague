-- Vue d'ensemble par patch : volume analysé et durée des parties.

with matches as (

    select * from {{ ref('stg_riot_matches') }}
    where queue_id = 420
      and game_duration_s >= 300
      and not ended_in_early_surrender

)

select
    patch,
    count(*)                                   as total_matches,
    round(avg(game_duration_s) / 60.0, 1)      as avg_duration_min,
    min(game_started_at)                       as first_game_at,
    max(game_started_at)                       as last_game_at
from matches
group by 1
