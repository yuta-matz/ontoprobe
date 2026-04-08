select
    o.order_id,
    o.customer_id,
    o.order_date,
    o.total_amount,
    o.discount_amount,
    o.campaign_id,
    c.customer_segment,
    c.region,
    extract(month from o.order_date) as order_month,
    extract(quarter from o.order_date) as order_quarter,
    case when o.campaign_id is not null then true else false end as has_campaign
from {{ ref('stg_orders') }} o
left join {{ ref('stg_customers') }} c using (customer_id)
