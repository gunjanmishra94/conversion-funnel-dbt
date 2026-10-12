-- Follows from the strict funnel: every step is a subset of the previous one,
-- so the conversion rate cannot leave the 0 to 100 range.

select *
from {{ ref('rep_conversion_funnel_monthly') }}
where conversion_from_previous_pct < 0
    or conversion_from_previous_pct > 100
