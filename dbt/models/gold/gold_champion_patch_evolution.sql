-- Évolution de la méta entre deux patchs consécutifs, enrichie par les notes
-- officielles afin de distinguer le constat statistique de son contexte.

with ordered as (

    select
        patch,
        champion_key,
        champion_name,
        picks,
        winrate,
        pickrate,
        row_number() over (
            partition by champion_key, patch
            order by champion_name
        ) as rn,
        split_part(patch, '.', 1)::int as patch_major,
        split_part(patch, '.', 2)::int as patch_minor
    from {{ ref('gold_champion_meta_by_patch') }}

),

changes as (

    select
        patch,
        champion_key,
        string_agg(change_text, E'\n' order by heading) as change_text,
        max(source_url) as source_url
    from {{ ref('gold_champion_patch_changes') }}
    group by 1, 2

),

with_previous as (

    select
        *,
        lag(patch) over champion_history as previous_patch,
        lag(picks) over champion_history as previous_picks,
        lag(winrate) over champion_history as previous_winrate,
        lag(pickrate) over champion_history as previous_pickrate
    from ordered
    where rn = 1
    window champion_history as (
        partition by champion_key
        order by patch_major, patch_minor
    )

)

select
    w.patch || '|' || w.champion_key::text as evolution_key,
    w.patch,
    w.previous_patch,
    w.champion_key,
    w.champion_name,
    w.picks,
    w.previous_picks,
    w.winrate,
    w.previous_winrate,
    round(w.winrate - w.previous_winrate, 4) as winrate_delta,
    w.pickrate,
    w.previous_pickrate,
    round(w.pickrate - w.previous_pickrate, 4) as pickrate_delta,
    case
        when w.previous_patch is null then 'nouveau'
        when w.winrate - w.previous_winrate >= 0.02 then 'forte hausse'
        when w.winrate - w.previous_winrate >= 0.005 then 'hausse'
        when w.winrate - w.previous_winrate <= -0.02 then 'forte baisse'
        when w.winrate - w.previous_winrate <= -0.005 then 'baisse'
        else 'stable'
    end as trend,
    c.change_text as official_change,
    c.source_url
from with_previous as w
left join changes as c
    on c.patch = w.patch
   and c.champion_key = w.champion_key
