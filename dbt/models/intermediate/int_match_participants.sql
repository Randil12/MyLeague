-- Participants enrichis des métadonnées match, filtrés sur le périmètre d'analyse :
-- ranked solo queue (420), remakes exclus (< 5 min ou early surrender).

with matches as (

    select * from {{ ref('stg_riot_matches') }}
    where queue_id = 420
      and game_duration_s >= 300
      and not ended_in_early_surrender

),

participants as (

    select * from {{ ref('stg_riot_participants') }}

)

select
    p.*,
    m.patch,
    m.game_version,
    m.game_duration_s,
    m.game_started_at,
    m.source_tier
from participants as p
inner join matches as m using (match_id)
