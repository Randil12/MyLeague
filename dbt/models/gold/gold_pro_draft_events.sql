{{ config(tags=['leaguepedia_active'], indexes=[{'columns':['patch','competition_region','role']}]) }}

with games as (
    select g.*, coalesce(nullif(t.payload->>'Region',''),'Non renseignée') as competition_region
    from {{ ref('stg_lp_scoreboard_games') }} g
    left join {{ source('raw','leaguepedia_tournaments') }} t on t.overview_page=g.tournament_page
    where g.patch is not null
), roles as (
    select game_id, team, champion,
        case when count(distinct role)=1 then min(role) end as role
    from {{ ref('gold_pro_player_games') }} group by game_id,team,champion
), picks as (
    select g.game_id,g.patch,g.competition_region,g.team1 as team,g.win_team,trim(c) as champion_name
    from games g cross join lateral unnest(string_to_array(g.team1_picks,',')) c
    union all
    select g.game_id,g.patch,g.competition_region,g.team2,g.win_team,trim(c)
    from games g cross join lateral unnest(string_to_array(g.team2_picks,',')) c
)
select p.game_id,p.patch,p.competition_region,p.champion_name,r.role,'pick'::text as event_type,
    case when p.win_team is not null and p.win_team<>'' then p.team=p.win_team end as win
from picks p left join roles r on r.game_id=p.game_id and r.team=p.team and r.champion=p.champion_name
where p.champion_name<>''
union all
select g.game_id,g.patch,g.competition_region,trim(c),null::text,'ban',null::boolean
from games g cross join lateral unnest(string_to_array(concat_ws(',',g.team1_bans,g.team2_bans),',')) c
where trim(c)<>''
