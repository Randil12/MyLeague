-- Changements d'équilibrage annoncés par champion et par patch.
-- Jointure des sections de notes de patch sur le référentiel des champions :
-- permet de corréler un nerf/buff annoncé avec la variation de winrate observée
-- (gold_champion_meta_by_patch) — l'analyse de causalité de la méta.

with sections as (

    select * from {{ ref('stg_riot_patch_note_sections') }}

),

champions as (

    select champion_key, name
    from (
        select
            champion_key,
            name,
            row_number() over (partition by champion_key order by loaded_at desc) as rn
        from {{ source('reference', 'dim_champion') }}
    ) as c
    where rn = 1

)

select
    s.patch,
    c.name        as champion_name,
    c.champion_key,
    s.heading,
    s.change_text,
    s.url         as source_url,
    s.scraped_at
from sections as s
inner join champions as c
    on lower(trim(s.heading)) = lower(c.name)
