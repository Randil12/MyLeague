select patch, champion_name, priority_score
from {{ ref('gold_draft_recommendations') }}
where priority_score not between 0 and 100
   or picks < 0
   or total_matches <= 0

