-- Recommandations de draft explicables : combinaison de la priorité ladder,
-- de la performance, de la méta professionnelle et de la robustesse de l'échantillon.

with ladder as (

    select
        b.patch,
        b.champion_key,
        b.champion_name,
        m.most_common_position,
        b.picks,
        b.matches_banned,
        b.total_matches,
        b.winrate,
        b.pickrate,
        b.banrate,
        b.presence
    from {{ ref('gold_champion_bans_by_patch') }} as b
    left join {{ ref('gold_champion_meta_by_patch') }} as m
        on m.patch = b.patch
       and m.champion_key = b.champion_key

),

enriched as (

    select
        l.*,
        p.picks as pro_picks,
        p.bans as pro_bans,
        p.total_games as pro_total_games,
        p.winrate as pro_winrate,
        p.presence as pro_presence,
        least(l.picks::numeric / 250.0, 1.0) as sample_factor,
        case
            when l.picks >= 250 then 'élevée'
            when l.picks >= 100 then 'moyenne'
            else 'faible'
        end as confidence_level
    from ladder as l
    left join {{ ref('gold_pro_champion_draft_by_patch') }} as p
        on p.patch = l.patch
       and lower(p.champion_name) = lower(l.champion_name)

),

scored as (

    select
        *,
        round(
            100 * (
                0.40 * coalesce(presence, 0)
                + 0.20 * greatest(coalesce(winrate, 0.5) - 0.45, 0)
                + 0.20 * coalesce(pro_presence, presence, 0)
                + 0.20 * sample_factor
            ),
            1
        ) as priority_score
    from enriched

)

select
    patch || '|' || champion_key::text as recommendation_key,
    patch,
    champion_key,
    champion_name,
    coalesce(most_common_position, 'UNKNOWN') as role,
    picks,
    matches_banned,
    total_matches,
    winrate,
    pickrate,
    banrate,
    presence,
    pro_picks,
    pro_bans,
    pro_total_games,
    pro_winrate,
    pro_presence,
    confidence_level,
    priority_score,
    case
        when confidence_level = 'faible' then 'À surveiller — échantillon insuffisant'
        when priority_score >= 65 then 'Priorité de pick / ban'
        when priority_score >= 45 then 'Pick de rotation'
        else 'Pick situationnel'
    end as recommendation
from scored

