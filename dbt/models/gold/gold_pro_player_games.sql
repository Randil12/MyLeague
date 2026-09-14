{{ config(tags=['leaguepedia_active'], indexes=[
    {'columns': ['season_year', 'player_page']},
    {'columns': ['game_id', 'player_page'], 'unique': True}
]) }}

-- One observed competitive participation; missing statistics remain NULL.
-- MediaWiki page identity ignores the case of the first character only.
-- Preserve the rest (including disambiguation), never merge by display name.
with normalized_players as (
    -- Observed G2 2026 spelling variant (capital I versus lowercase l).
    -- Scope the correction to this team/year; never fuzzy-merge all player names.
    select *, case when player_page='BrokenBIade' and payload->>'Team'='G2 Esports'
                           and game_date >= '2026-01-01'::timestamptz
                           and game_date < '2027-01-01'::timestamptz
                      then 'BrokenBlade'
                  else upper(left(player_page, 1)) || substring(player_page from 2)
              end as canonical_page
    from {{ source('raw', 'leaguepedia_scoreboard_players') }}
), participations as (
    select distinct on (game_id, canonical_page)
        game_id, canonical_page as player_page, champion, role, payload, loaded_at
    from normalized_players
    order by game_id, canonical_page, loaded_at desc, player_page
), identities as (
    select distinct on (upper(left(overview_page, 1)) || substring(overview_page from 2))
        upper(left(overview_page, 1)) || substring(overview_page from 2) as overview_page,
        payload
    from {{ source('raw', 'leaguepedia_players') }}
    order by upper(left(overview_page, 1)) || substring(overview_page from 2),
        loaded_at desc, overview_page
)
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
    (p.payload ?& array['Items','Trinket','KeystoneRune','PrimaryTree','SecondaryTree','Runes'])
        as equipment_fields_collected,
    case when coalesce(g.payload ->> 'Gamelength_Number', g.payload ->> 'Gamelength Number') ~ '^[0-9]+([.][0-9]+)?$'
         then nullif(coalesce(g.payload ->> 'Gamelength_Number', g.payload ->> 'Gamelength Number')::numeric, 0)
         end as duration_min,
    greatest(p.loaded_at, g.loaded_at) as loaded_at
from participations p
join {{ source('raw', 'leaguepedia_scoreboard_games') }} g using (game_id)
left join {{ source('raw', 'leaguepedia_tournaments') }} t
    on t.overview_page = g.payload ->> 'OverviewPage'
left join identities identity
    on identity.overview_page = p.player_page
where g.game_date is not null
