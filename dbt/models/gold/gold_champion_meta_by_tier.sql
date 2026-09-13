-- Méta par niveau de jeu : la méta Master+ n'est pas la méta Diamond/Emerald.
-- Le tier est celui du joueur source ayant fait découvrir le match
-- (approximation raisonnable : le matchmaking regroupe des elos proches).

with participants as (

    select * from {{ ref('int_match_participants') }}

),

matches_per_patch_tier as (

    select
        patch,
        coalesce(source_tier, 'UNKNOWN') as tier,
        count(distinct match_id)         as total_matches
    from participants
    group by 1, 2

)

select
    p.patch,
    coalesce(p.source_tier, 'UNKNOWN')                       as tier,
    p.champion_name,
    count(*)                                                 as picks,
    sum(case when p.win then 1 else 0 end)                   as wins,
    round(avg(case when p.win then 1.0 else 0.0 end), 4)     as winrate,
    round(
        (sum(p.kills) + sum(p.assists))::numeric
        / nullif(sum(p.deaths), 0),
        2
    )                                                        as kda,
    m.total_matches                                          as matches_in_patch_tier,
    round(count(*)::numeric / m.total_matches, 4)            as pickrate
from participants as p
inner join matches_per_patch_tier as m
    on m.patch = p.patch
   and m.tier = coalesce(p.source_tier, 'UNKNOWN')
group by 1, 2, 3, m.total_matches
