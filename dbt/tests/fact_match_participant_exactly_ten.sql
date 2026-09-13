-- Chaque match retenu pour l'analyse doit contenir exactement dix participants.
select match_id, count(*) as participant_count
from {{ ref('fact_match_participant') }}
group by 1
having count(*) <> 10

