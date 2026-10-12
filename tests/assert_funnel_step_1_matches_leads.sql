-- Step 1 must account for every cleaned lead exactly once, in the month it
-- was created. Catches leads lost or multiplied by the joins.

with leads as (

    select
        {{ month_start('created_at') }} as lead_month,
        count(*) as lead_count
    from {{ ref('stg_leads') }}
    group by 1

),

funnel as (

    select "month" as lead_month, "count" as lead_count
    from {{ ref('rep_conversion_funnel_monthly') }}
    where funnel_step = 1

)

select
    coalesce(leads.lead_month, funnel.lead_month) as lead_month,
    leads.lead_count as leads_in_staging,
    funnel.lead_count as leads_in_funnel
from leads
full outer join funnel
    on leads.lead_month = funnel.lead_month
where leads.lead_count is distinct from funnel.lead_count
