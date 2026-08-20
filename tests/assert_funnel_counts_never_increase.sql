-- Strict funnel: within a month a step can never have more leads than the
-- step before it. Returns the rows that break this.

with funnel as (

    select
        "month",
        funnel_step,
        "count" as lead_count,
        lag("count") over (partition by "month" order by funnel_step) as previous_count
    from {{ ref('rep_conversion_funnel_monthly') }}

)

select *
from funnel
where lead_count > previous_count
