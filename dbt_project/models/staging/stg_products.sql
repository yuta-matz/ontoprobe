select
    product_id,
    name as product_name,
    category_id,
    price,
    is_seasonal
from {{ source('raw', 'products') }}
