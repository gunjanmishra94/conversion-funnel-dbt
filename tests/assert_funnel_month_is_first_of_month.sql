-- month is the start of the cohort month.

select *
from {{ ref('rep_conversion_funnel_monthly') }}
where "month" <> {{ month_start('"month"') }}
