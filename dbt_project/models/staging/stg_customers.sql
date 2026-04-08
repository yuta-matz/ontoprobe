select
    customer_id,
    email,
    signup_date,
    region,
    customer_segment
from {{ source('raw', 'customers') }}
