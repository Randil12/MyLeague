{{ config(tags=['leaguepedia_active']) }}

select
    season_year, player_page, source_patch, role, champion,
    count(*) as games,
    count(win) as games_with_result,
    count(*) filter (where win) as wins,
    avg(win::int)::numeric as winrate,
    count(*) filter (where kills is not null and deaths is not null
                    and assists is not null) as games_with_kda,
    avg(kills) as avg_kills,
    avg(deaths) as avg_deaths,
    avg(assists) as avg_assists,
    avg(cs) as avg_cs,
    avg(gold) as avg_gold,
    -- Ratio of totals, complete KDA rows only; deathless groups return NULL.
    sum(kills + assists) filter (where deaths is not null)
      / nullif(sum(deaths) filter (where kills is not null and assists is not null), 0)
      as kda,
    max(game_date) as last_game_at
from {{ ref('gold_pro_player_games') }}
group by season_year, player_page, source_patch, role, champion
