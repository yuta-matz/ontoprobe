select
    order_id,
    customer_id,
    order_date,
    total_amount,
    discount_amount,
    campaign_id,
    status
from {{ source('raw', 'orders') }}
where status = 'completed'
