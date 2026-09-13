-- Méta par champion et par patch : picks, winrate, pickrate, KDA, CS/min.
-- Table centrale pour les recommandations de draft de Nexus Esport Academy.

with participants as (

    select * from {{ ref('int_match_participants') }}

),

matches_per_patch as (

    select
        patch,
        count(distinct match_id) as total_matches
    from participants
    group by 1

),

champion_stats as (

    select
        p.patch,
        p.champion_name,
        max(p.champion_key)                                          as champion_key,
        count(*)                                                     as picks,
        sum(case when p.win then 1 else 0 end)                       as wins,
        round(avg(case when p.win then 1.0 else 0.0 end), 4)         as winrate,
        round(avg(p.kills), 2)                                       as avg_kills,
        round(avg(p.deaths), 2)                                      as avg_deaths,
        round(avg(p.assists), 2)                                     as avg_assists,
        round(
            (sum(p.kills) + sum(p.assists))::numeric
            / nullif(sum(p.deaths), 0),
            2
        )                                                            as kda,
        round(avg(p.total_cs / (p.game_duration_s / 60.0)), 2)       as avg_cs_per_min,
        round(avg(p.gold_earned), 0)                                 as avg_gold,
        round(avg(p.damage_to_champions), 0)                         as avg_damage_to_champions,
        mode() within group (order by p.team_position)               as most_common_position
    from participants as p
    group by 1, 2

)

select
    c.*,
    m.total_matches                                     as matches_in_patch,
    round(c.picks::numeric / m.total_matches, 4)        as pickrate
from champion_stats as c
inner join matches_per_patch as m using (patch)
