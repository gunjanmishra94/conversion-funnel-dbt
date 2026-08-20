-- Grain: one row per month and step, and every month has steps 1 to 6.

select
    "month",
    count(*) as row_count,
    count(distinct funnel_step) as step_count
from {{ ref('rep_conversion_funnel_monthly') }}
group by "month"
having count(*) <> 6 or count(distinct funnel_step) <> 6
