with customers as (
    select * from {{ ref('stg_customers') }}
),

order_stats as (
    select
        customer_id,
        count(*) as total_orders,
        sum(total_amount) as lifetime_revenue,
        avg(total_amount) as avg_order_value,
        min(order_date) as first_order_date,
        max(order_date) as last_order_date
    from {{ ref('stg_orders') }}
    group by customer_id
)

select
    c.customer_id,
    c.email,
    c.signup_date,
    c.region,
    c.customer_segment,
    coalesce(o.total_orders, 0) as total_orders,
    coalesce(o.lifetime_revenue, 0) as lifetime_revenue,
    coalesce(o.avg_order_value, 0) as avg_order_value,
    o.first_order_date,
    o.last_order_date
from customers c
left join order_stats o using (customer_id)
