-- Une ligne retournée représente une anomalie de cohérence métier.
select patch, champion_name, winrate, pickrate, picks, matches_in_patch
from {{ ref('gold_champion_meta_by_patch') }}
where winrate not between 0 and 1
   or pickrate not between 0 and 1
   or picks < 0
   or picks > matches_in_patch

