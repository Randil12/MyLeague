-- Écart entre les champions prioritaires du patch courant et la maîtrise des
-- joueurs de l'academy. Une ligne représente un joueur et un champion de la méta.

with current_patch as (

    select patch
    from {{ ref('gold_patch_summary') }}
    order by
        split_part(patch, '.', 1)::int desc,
        split_part(patch, '.', 2)::int desc
    limit 1

),

academy_players as (

    select
        puuid,
        coalesce(riot_summoner_name, left(puuid, 12) || '…') as player_name,
        tier,
        rank
    from {{ source('audit', 'riot_tracked_players') }}
    where is_tracked
      and tracking_source = 'academy'

),

meta as (

    select r.*
    from {{ ref('gold_draft_recommendations') }} as r
    inner join current_patch as p using (patch)
    where r.confidence_level <> 'faible'

),

masteries as (

    select * from {{ source('raw', 'riot_champion_masteries') }}

)

select
    p.puuid || '|' || m.patch || '|' || m.champion_key::text as pool_gap_key,
    p.puuid,
    p.player_name,
    p.tier,
    p.rank,
    m.patch,
    m.champion_key,
    m.champion_name,
    m.role,
    m.priority_score,
    m.recommendation,
    coalesce(ms.mastery_level, 0) as mastery_level,
    coalesce(ms.mastery_points, 0) as mastery_points,
    ms.last_played_at,
    case
        when coalesce(ms.mastery_points, 0) >= 100000 then 'prêt'
        when coalesce(ms.mastery_points, 0) >= 50000 then 'à consolider'
        when coalesce(ms.mastery_points, 0) >= 10000 then 'en apprentissage'
        else 'à acquérir'
    end as readiness,
    round(
        m.priority_score
        * case
            when coalesce(ms.mastery_points, 0) >= 100000 then 0.10
            when coalesce(ms.mastery_points, 0) >= 50000 then 0.35
            when coalesce(ms.mastery_points, 0) >= 10000 then 0.70
            else 1.00
        end,
        1
    ) as training_priority
from academy_players as p
cross join meta as m
left join masteries as ms
    on ms.puuid = p.puuid
   and ms.champion_key = m.champion_key

