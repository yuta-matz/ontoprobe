select
    campaign_id,
    campaign_name,
    campaign_type,
    start_date,
    end_date,
    discount_percent
from {{ source('raw', 'campaigns') }}
