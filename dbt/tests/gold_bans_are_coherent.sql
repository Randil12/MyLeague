select patch, champion_name, pickrate, banrate, presence
from {{ ref('gold_champion_bans_by_patch') }}
where pickrate not between 0 and 1
   or banrate not between 0 and 1
   or presence < pickrate
   or presence < banrate

