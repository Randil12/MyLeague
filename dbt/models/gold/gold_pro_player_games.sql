{{ config(tags=['leaguepedia_active']) }}

-- One observed competitive participation; missing statistics remain NULL.
select
    p.game_id,
    p.player_page,
    p.player_page as player_name,
    extract(year from g.game_date at time zone 'UTC')::int as season_year,
    g.game_date,
    g.patch as source_patch,
    g.payload ->> 'Tournament' as tournament,
    g.payload ->> 'OverviewPage' as tournament_page,
    nullif(p.payload ->> 'Team', '') as team,
    p.champion,
    p.role,
    case
        when nullif(g.payload ->> 'WinTeam', '') is not null
            and nullif(p.payload ->> 'Team', '') in
                (g.payload ->> 'Team1', g.payload ->> 'Team2')
        then (p.payload ->> 'Team') = (g.payload ->> 'WinTeam')
    end as win,
    {% for key in ['Kills', 'Deaths', 'Assists', 'CS', 'Gold'] %}
    case when p.payload ->> '{{ key }}' ~ '^[0-9]+$'
         then (p.payload ->> '{{ key }}')::numeric end as {{ key | lower }},
    {% endfor %}
    greatest(p.loaded_at, g.loaded_at) as loaded_at
from {{ source('raw', 'leaguepedia_scoreboard_players') }} p
join {{ source('raw', 'leaguepedia_scoreboard_games') }} g using (game_id)
where g.game_date is not null
