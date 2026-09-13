-- Runes : winrate des keystones par champion et par patch ("les pages qui gagnent").

with participants as (

    select * from {{ ref('int_match_participants') }}
    where keystone_id is not null

),

rune_names as (

    select rune_id, rune_name, style_name
    from (
        select
            rune_id,
            rune_name,
            style_name,
            row_number() over (partition by rune_id order by loaded_at desc) as rn
        from {{ source('reference', 'dim_rune') }}
    ) as d
    where rn = 1

)

select
    p.patch,
    p.champion_name,
    p.keystone_id,
    coalesce(r.rune_name, 'rune_' || p.keystone_id)          as keystone_name,
    r.style_name,
    count(*)                                                 as picks,
    round(avg(case when p.win then 1.0 else 0.0 end), 4)     as winrate
from participants as p
left join rune_names as r on r.rune_id = p.keystone_id
group by 1, 2, 3, 4, 5
