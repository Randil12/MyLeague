-- Draft : banrate et presence (pick + ban) par champion et par patch.
-- La presence est LA métrique de priorité de draft pour les coachs.

with matches as (

    select * from {{ ref('stg_riot_matches') }}
    where queue_id = 420
      and game_duration_s >= 300
      and not ended_in_early_surrender

),

total as (

    select patch, count(*) as total_matches
    from matches
    group by 1

),

bans as (

    select
        m.patch,
        b.champion_key,
        count(distinct b.match_id) as matches_banned
    from {{ ref('stg_riot_team_bans') }} as b
    inner join matches as m using (match_id)
    group by 1, 2

),

picks as (

    select patch, champion_key, champion_name, picks, winrate
    from {{ ref('gold_champion_meta_by_patch') }}

),

champions as (

    select champion_key, name
    from (
        select
            champion_key,
            name,
            row_number() over (partition by champion_key order by loaded_at desc) as rn
        from {{ source('reference', 'dim_champion') }}
    ) as c
    where rn = 1

)

select
    coalesce(b.patch, p.patch)                                        as patch,
    coalesce(b.champion_key, p.champion_key)                          as champion_key,
    coalesce(p.champion_name, c.name,
             'champion_' || coalesce(b.champion_key, p.champion_key)) as champion_name,
    coalesce(p.picks, 0)                                              as picks,
    p.winrate,
    coalesce(b.matches_banned, 0)                                     as matches_banned,
    t.total_matches,
    round(coalesce(b.matches_banned, 0)::numeric / t.total_matches, 4) as banrate,
    round(coalesce(p.picks, 0)::numeric / t.total_matches, 4)          as pickrate,
    round(
        (coalesce(p.picks, 0) + coalesce(b.matches_banned, 0))::numeric / t.total_matches,
        4
    )                                                                  as presence
from bans as b
full outer join picks as p
    on p.patch = b.patch and p.champion_key = b.champion_key
inner join total as t
    on t.patch = coalesce(b.patch, p.patch)
left join champions as c
    on c.champion_key = coalesce(b.champion_key, p.champion_key)
