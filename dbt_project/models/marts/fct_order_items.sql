select
    oi.order_item_id,
    oi.order_id,
    oi.product_id,
    oi.quantity,
    oi.unit_price,
    oi.line_total,
    p.product_name,
    p.is_seasonal,
    p.category_name,
    o.order_date,
    o.customer_segment,
    extract(month from o.order_date) as order_month,
    extract(quarter from o.order_date) as order_quarter
from {{ ref('stg_order_items') }} oi
left join {{ ref('dim_products') }} p using (product_id)
left join {{ ref('fct_orders') }} o using (order_id)
