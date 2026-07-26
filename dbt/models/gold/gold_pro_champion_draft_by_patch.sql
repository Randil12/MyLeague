-- Méta professionnelle par patch : picks, bans, presence et winrate en compétition.
-- Le format de patch (ex : 16.13) est identique à celui des matchs solo queue :
-- cette table se compare directement à gold_champion_meta_by_patch (pro vs ladder).

with games as (

    select * from {{ ref('stg_lp_scoreboard_games') }}
    where patch is not null

),

total as (

    select patch, count(*) as total_games
    from games
    group by 1

),

picks as (

    select g.patch, g.game_id, trim(p.champ) as champion_name, (g.team1 = g.win_team) as win
    from games as g
    cross join lateral unnest(string_to_array(g.team1_picks, ',')) as p (champ)
    where g.team1_picks is not null

    union all

    select g.patch, g.game_id, trim(p.champ), (g.team2 = g.win_team)
    from games as g
    cross join lateral unnest(string_to_array(g.team2_picks, ',')) as p (champ)
    where g.team2_picks is not null

),

bans as (

    select g.patch, g.game_id, trim(b.champ) as champion_name
    from games as g
    cross join lateral unnest(
        string_to_array(concat_ws(',', g.team1_bans, g.team2_bans), ',')
    ) as b (champ)

),

pick_stats as (

    select
        patch,
        champion_name,
        count(*)                                             as picks,
        sum(case when win then 1 else 0 end)                 as wins,
        round(avg(case when win then 1.0 else 0.0 end), 4)   as winrate
    from picks
    where champion_name <> ''
    group by 1, 2

),

ban_stats as (

    select patch, champion_name, count(*) as bans
    from bans
    where champion_name <> ''
    group by 1, 2

)

select
    coalesce(p.patch, b.patch)                                         as patch,
    coalesce(p.champion_name, b.champion_name)                         as champion_name,
    coalesce(p.picks, 0)                                               as picks,
    coalesce(p.wins, 0)                                                as wins,
    p.winrate,
    coalesce(b.bans, 0)                                                as bans,
    t.total_games,
    round(coalesce(p.picks, 0)::numeric / t.total_games, 4)            as pickrate,
    round(coalesce(b.bans, 0)::numeric / t.total_games, 4)             as banrate,
    round(
        (coalesce(p.picks, 0) + coalesce(b.bans, 0))::numeric / t.total_games, 4
    )                                                                  as presence
from pick_stats as p
full outer join ban_stats as b
    on b.patch = p.patch and b.champion_name = p.champion_name
inner join total as t
    on t.patch = coalesce(p.patch, b.patch)
