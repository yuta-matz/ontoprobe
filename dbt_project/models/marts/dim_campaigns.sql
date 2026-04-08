select
    campaign_id,
    campaign_name,
    campaign_type,
    start_date,
    end_date,
    discount_percent,
    end_date - start_date + 1 as duration_days
from {{ ref('stg_campaigns') }}
