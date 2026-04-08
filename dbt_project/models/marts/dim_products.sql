with products as (
    select * from {{ ref('stg_products') }}
),

categories as (
    select
        category_id,
        category_name,
        parent_category_id
    from {{ source('raw', 'product_categories') }}
)

select
    p.product_id,
    p.product_name,
    p.price,
    p.is_seasonal,
    c.category_name,
    pc.category_name as parent_category_name
from products p
left join categories c using (category_id)
left join categories pc on c.parent_category_id = pc.category_id
