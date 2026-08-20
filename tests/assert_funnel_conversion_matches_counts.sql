-- The rate must be count / previous count * 100, rounded to one decimal.
-- It is null for step 1 and when the previous step is 0, and only then.

with funnel as (

    select
        *,
        lag("count") over (partition by "month" order by funnel_step) as previous_count
    from {{ ref('rep_conversion_funnel_monthly') }}

),

expected as (

    select
        *,
        {{ conversion_pct('"count"', 'previous_count') }} as expected_pct
    from funnel

)

select *
from expected
where conversion_from_previous_pct is distinct from expected_pct
