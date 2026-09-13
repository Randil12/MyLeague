{{ config(tags=['leaguepedia_active']) }}

-- Activity is observed participation, not employment or current retirement status.
select
    season_year,
    player_page,
    max(player_name) as player_name,
    min(game_date) as first_game_at,
    max(game_date) as last_game_at,
    count(*) as games,
    count(distinct champion) as champions_played,
    count(distinct tournament_page) as tournaments_played,
    count(win) as games_with_result,
    count(*) filter (where win) as wins,
    avg(win::int)::numeric as winrate,
    max(loaded_at) as loaded_at
from {{ ref('gold_pro_player_games') }}
group by season_year, player_page
