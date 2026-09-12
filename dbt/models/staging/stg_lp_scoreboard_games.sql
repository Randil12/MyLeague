-- Parties professionnelles Leaguepedia : une partie par ligne, picks/bans en texte brut.

with source as (

    select * from {{ source('raw', 'leaguepedia_scoreboard_games') }}

),

typed as (

    select
        *,
        nullif(coalesce(payload ->> 'Patch', patch), '') as source_patch
    from source

)

select
    game_id,
    payload ->> 'Tournament'   as tournament,
    payload ->> 'OverviewPage' as tournament_page,
    payload ->> 'Team1'        as team1,
    payload ->> 'Team2'        as team2,
    payload ->> 'WinTeam'      as win_team,
    source_patch,
    case
        -- Depuis 2025, Leaguepedia préfixe le patch par l'année (26.14),
        -- tandis que le gameVersion Riot utilisé par l'entrepôt reste 16.14.
        -- Les deux valeurs décrivent le même patch : on conserve la source et
        -- on normalise uniquement la clé analytique.
        when source_patch ~ '^[0-9]+\.[0-9]+$'
             and split_part(source_patch, '.', 1)::int >= 25
        then (split_part(source_patch, '.', 1)::int - 10)::text
             || '.' || split_part(source_patch, '.', 2)
        else source_patch
    end as patch,
    game_date,
    payload ->> 'Team1Picks'   as team1_picks,
    payload ->> 'Team2Picks'   as team2_picks,
    payload ->> 'Team1Bans'    as team1_bans,
    payload ->> 'Team2Bans'    as team2_bans
from typed
