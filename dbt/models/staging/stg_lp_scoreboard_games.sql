-- Parties professionnelles Leaguepedia : une partie par ligne, picks/bans en texte brut.

with source as (

    select * from {{ source('raw', 'leaguepedia_scoreboard_games') }}

)

select
    game_id,
    payload ->> 'Tournament'   as tournament,
    payload ->> 'OverviewPage' as tournament_page,
    payload ->> 'Team1'        as team1,
    payload ->> 'Team2'        as team2,
    payload ->> 'WinTeam'      as win_team,
    nullif(coalesce(payload ->> 'Patch', patch), '') as patch,
    game_date,
    payload ->> 'Team1Picks'   as team1_picks,
    payload ->> 'Team2Picks'   as team2_picks,
    payload ->> 'Team1Bans'    as team1_bans,
    payload ->> 'Team2Bans'    as team2_bans
from source
