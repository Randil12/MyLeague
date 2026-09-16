{{ config(indexes=[{'columns':['match_id','puuid'],'unique':True},
                   {'columns':['puuid','patch','game_started_at']}]) }}

-- One participant per match. A missing observation is never a zero.
with participants as (
    select m.match_id, p->>'puuid' as puuid, p->>'participantId' as participant_id,
        case when p->'challenges'->>'soloKills' ~ '^[0-9]+$'
             then (p->'challenges'->>'soloKills')::int end as solo_kills,
        case when p->>'wardsPlaced' ~ '^[0-9]+$'
             then (p->>'wardsPlaced')::bigint end as wards_placed,
        case when p->>'detectorWardsPlaced' ~ '^[0-9]+$'
             then (p->>'detectorWardsPlaced')::bigint end as control_wards_placed,
        case when p->>'visionWardsBoughtInGame' ~ '^[0-9]+$'
             then (p->>'visionWardsBoughtInGame')::bigint end as control_wards_bought
    from {{ source('raw','riot_matches') }} m
    cross join lateral jsonb_array_elements(m.payload->'info'->'participants') p
), frames as (
    select t.match_id, f, (f->>'timestamp')::bigint as ts,
        (f->>'timestamp')::bigint - lag((f->>'timestamp')::bigint)
            over(partition by t.match_id order by (f->>'timestamp')::bigint) as gap
    from {{ source('raw','riot_match_timelines') }} t
    cross join lateral jsonb_array_elements(
        case when jsonb_typeof(t.payload->'info'->'frames')='array'
             then t.payload->'info'->'frames' else '[]'::jsonb end) f
    where f->>'timestamp' ~ '^[0-9]+$'
), coverage as (
    select match_id, min(ts)<=1000 and max(ts)>=900000
        and coalesce(max(gap) filter(where ts-coalesce(gap,0)<900000),0)<=90000
        and bool_and(jsonb_typeof(f->'events')='array' and f ? 'events')
            filter(where ts-coalesce(gap,0)<900000) as events_complete,
        min(ts)<=1000 and coalesce(max(gap),0)<=90000
            and bool_and(jsonb_typeof(f->'events')='array' and f ? 'events') as full_events_contiguous,
        max(ts) as last_frame_ms
    from frames group by match_id
), observation as (
    select distinct on(match_id) match_id, ts, f
    from frames where abs(ts-900000)<=5000
    order by match_id, abs(ts-900000), ts
), all_solo_events as (
    select distinct match_id, e
    from frames cross join lateral jsonb_array_elements(
        case when jsonb_typeof(f->'events')='array' then f->'events' else '[]'::jsonb end) e
    where e->>'type'='CHAMPION_KILL'
      and e->>'timestamp' ~ '^[0-9]+$'
      -- Riot omits assistingParticipantIds when there are no recorded assists.
      and (not e ? 'assistingParticipantIds' or e->'assistingParticipantIds'='[]'::jsonb)
      and e->>'killerId' ~ '^[1-9][0-9]*$'
      and e->>'victimId' ~ '^[1-9][0-9]*$'
), events as (
    select * from all_solo_events where (e->>'timestamp')::bigint < 900000
), duels as (
    select match_id, e->>'killerId' as killer, e->>'victimId' as victim,
        count(*) as kills
    from all_solo_events group by match_id, e->>'killerId', e->>'victimId'
), solo as (
    select match_id, participant_id, sum(kills) as kills, sum(deaths) as deaths
    from (
        select match_id, e->>'killerId' as participant_id, 1 as kills, 0 as deaths from events
        union all
        select match_id, e->>'victimId', 0, 1 from events
    ) counts group by match_id, participant_id
), base as (
    select f.*, p.participant_id, p.solo_kills,
        p.wards_placed, p.control_wards_placed, p.control_wards_bought,
        c.full_events_contiguous and f.game_duration_s>0
            and c.last_frame_ms>=f.game_duration_s*1000-5000 as full_timeline_available,
        case when f.game_duration_s>=900 then o.ts end as observed_at_ms,
        case when f.game_duration_s>=900 then o.f->'participantFrames'->p.participant_id end as pf,
        case when f.game_duration_s>=900 and c.events_complete and p.participant_id is not null
             then coalesce(s.kills,0) end as solo_kills_15,
        case when f.game_duration_s>=900 and c.events_complete and p.participant_id is not null
             then coalesce(s.deaths,0) end as solo_deaths_15,
        count(*) over(partition by f.match_id,f.team_id,f.team_position) as role_count
    from {{ ref('fact_match_participant') }} f
    left join participants p on p.match_id=f.match_id and p.puuid=f.puuid
    left join observation o on o.match_id=f.match_id
    left join coverage c on c.match_id=f.match_id
    left join solo s on s.match_id=f.match_id and s.participant_id=p.participant_id
), measured as (
    select *,
        case when pf->>'totalGold' ~ '^[0-9]+$' then (pf->>'totalGold')::int end as gold_15,
        case when pf->>'minionsKilled' ~ '^[0-9]+$' and pf->>'jungleMinionsKilled' ~ '^[0-9]+$'
             then (pf->>'minionsKilled')::int+(pf->>'jungleMinionsKilled')::int end as cs_15,
        case when pf->>'xp' ~ '^[0-9]+$' then (pf->>'xp')::int end as xp_15
    from base
)
select a.match_id, a.puuid, a.champion_name, a.team_position as role, a.patch,
    a.game_started_at, a.win, a.solo_kills, a.solo_kills_15, a.solo_deaths_15,
    a.wards_placed, a.control_wards_placed, a.control_wards_bought,
    a.observed_at_ms, a.gold_15, a.cs_15, a.xp_15,
    case when a.game_duration_s>0 and a.damage_to_champions>=0
         then a.damage_to_champions::numeric*60/a.game_duration_s end as damage_min,
    case when a.game_duration_s>0 and a.total_cs>=0
         then a.total_cs::numeric*60/a.game_duration_s end as cs_min,
    b.champion_name as opponent,
    a.gold_15-b.gold_15 as gd_15, a.cs_15-b.cs_15 as csd_15, a.xp_15-b.xp_15 as xpd_15,
    case when a.full_timeline_available and a.participant_id is not null and b.participant_id is not null
         then coalesce(ab.kills,0) end as solo_kills_vs_opponent,
    case when a.full_timeline_available and a.participant_id is not null and b.participant_id is not null
         then coalesce(ba.kills,0) end as solo_deaths_vs_opponent
from measured a
left join measured b on b.match_id=a.match_id and b.team_position=a.team_position
    and b.team_id<>a.team_id and a.role_count=1 and b.role_count=1
    and a.team_position in ('TOP','JUNGLE','MIDDLE','BOTTOM','UTILITY')
left join duels ab on ab.match_id=a.match_id and ab.killer=a.participant_id and ab.victim=b.participant_id
left join duels ba on ba.match_id=a.match_id and ba.killer=b.participant_id and ba.victim=a.participant_id
