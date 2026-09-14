{{ config(tags=['leaguepedia_active'], indexes=[
    {'columns': ['season_year', 'player_page']},
    {'columns': ['game_id', 'player_page'], 'unique': True}
]) }}

-- One observed competitive participation; missing statistics remain NULL.
select
    p.game_id,
    p.player_page,
    coalesce(nullif(identity.payload ->> 'ID', ''), p.player_page) as player_name,
    nullif(identity.payload ->> 'SoloqueueIds', '') as reported_soloqueue_accounts,
    extract(year from g.game_date at time zone 'UTC')::int as season_year,
    g.game_date,
    g.patch as source_patch,
    coalesce(nullif(t.payload ->> 'Name', ''), g.payload ->> 'Tournament') as tournament,
    g.payload ->> 'OverviewPage' as tournament_page,
    coalesce(nullif(t.payload ->> 'Region', ''), 'Non renseignée') as competition_region,
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
    case when p.payload ->> 'DamageToChampions' ~ '^[0-9]+$'
         then (p.payload ->> 'DamageToChampions')::numeric end as damage_to_champions,
    case when p.payload ->> 'VisionScore' ~ '^[0-9]+$'
         then (p.payload ->> 'VisionScore')::numeric end as vision_score,
    nullif(p.payload ->> 'Items', '') as items,
    nullif(p.payload ->> 'Trinket', '') as trinket,
    nullif(p.payload ->> 'KeystoneRune', '') as keystone_rune,
    nullif(p.payload ->> 'PrimaryTree', '') as primary_tree,
    nullif(p.payload ->> 'SecondaryTree', '') as secondary_tree,
    nullif(p.payload ->> 'Runes', '') as runes,
    case when coalesce(g.payload ->> 'Gamelength_Number', g.payload ->> 'Gamelength Number') ~ '^[0-9]+([.][0-9]+)?$'
         then nullif(coalesce(g.payload ->> 'Gamelength_Number', g.payload ->> 'Gamelength Number')::numeric, 0)
         end as duration_min,
    greatest(p.loaded_at, g.loaded_at) as loaded_at
from {{ source('raw', 'leaguepedia_scoreboard_players') }} p
join {{ source('raw', 'leaguepedia_scoreboard_games') }} g using (game_id)
left join {{ source('raw', 'leaguepedia_tournaments') }} t
    on t.overview_page = g.payload ->> 'OverviewPage'
left join {{ source('raw', 'leaguepedia_players') }} identity
    on identity.overview_page = p.player_page
where g.game_date is not null
