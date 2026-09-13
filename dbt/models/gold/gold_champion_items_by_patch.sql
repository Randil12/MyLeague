-- Builds : winrate des items par champion et par patch ("les builds qui gagnent").
-- Les 6 slots d'items sont dépivotés ; le trinket (slot 6) est exclu.

with participants as (

    select * from {{ ref('int_match_participants') }}

),

items as (

    select
        p.patch,
        p.champion_name,
        i.item_key,
        p.win
    from participants as p
    cross join lateral unnest(
        array[p.item0, p.item1, p.item2, p.item3, p.item4, p.item5]
    ) as i (item_key)
    where i.item_key is not null
      and i.item_key > 0

),

item_names as (

    select item_id, name
    from (
        select
            item_id,
            name,
            row_number() over (partition by item_id order by loaded_at desc) as rn
        from {{ source('reference', 'dim_item') }}
    ) as d
    where rn = 1

)

select
    i.patch,
    i.champion_name,
    i.item_key,
    coalesce(n.name, 'item_' || i.item_key)                  as item_name,
    count(*)                                                 as times_built,
    round(avg(case when i.win then 1.0 else 0.0 end), 4)     as winrate
from items as i
left join item_names as n on n.item_id = i.item_key
group by 1, 2, 3, 4
