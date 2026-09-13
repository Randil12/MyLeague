-- Sections des notes de patch scrapées : une section (titre + texte) par ligne.

with source as (

    select * from {{ source('raw', 'riot_patch_notes') }}

)

select
    s.patch,
    s.url,
    s.title           as page_title,
    sec.value ->> 'heading' as heading,
    sec.value ->> 'level'   as heading_level,
    sec.value ->> 'text'    as change_text,
    s.scraped_at
from source as s
cross join lateral jsonb_array_elements(s.payload -> 'sections') as sec (value)
