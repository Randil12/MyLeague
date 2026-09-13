{{ config(severity='warn') }}

-- Quand les deux jeux de données sont alimentés, au moins un patch commun doit
-- permettre la comparaison pro / solo queue. Une absence totale signale le plus
-- souvent une convention de numérotation différente ou une source obsolète.
with solo as (
    select distinct patch from {{ ref('gold_champion_meta_by_patch') }}
),
pro as (
    select distinct patch from {{ ref('gold_pro_champion_draft_by_patch') }}
),
source_state as (
    select
        (select count(*) from solo) as solo_count,
        (select count(*) from pro) as pro_count,
        (select count(*) from solo inner join pro using (patch)) as overlap_count
)
select *
from source_state
where solo_count > 0
  and pro_count > 0
  and overlap_count = 0
