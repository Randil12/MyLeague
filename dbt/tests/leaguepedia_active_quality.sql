{{ config(tags=['leaguepedia_active']) }}

select 'duplicate_participation' as issue
from {{ ref('gold_pro_player_games') }}
group by game_id, player_page having count(*) > 1
union all
select 'duplicate_active_player'
from {{ ref('gold_pro_active_players_year') }}
group by season_year, player_page having count(*) > 1
union all
select 'invalid_comparison'
from {{ ref('gold_pro_player_comparison') }}
where games < 1 or games_with_result > games or wins > games_with_result
   or winrate < 0 or winrate > 1
