-- Monthly funnel from lead created to first delivery.
--
-- Everything is counted in the lead's creation month (cohort), not in the
-- month the opportunity, subscription or delivery happened.
-- Counts are strict: a lead only counts at step N if it also reached 1..N-1.
--
-- One row per month and step, and every month gets all six steps.

with lead_stages as (

    select * from {{ ref('int_lead_funnel_stages') }}

),

funnel_steps as (

    select *
    from (
        values
            (1, 'Lead Created'),
            (2, 'Lead Qualified'),
            (3, 'Lead Converted'),
            (4, 'Opportunity Won'),
            (5, 'Subscription Active'),
            (6, 'First Delivery')
    ) as steps (funnel_step, kpi_name)

),

step_counts as (

    select
        lead_stages.lead_month,
        funnel_steps.funnel_step,
        funnel_steps.kpi_name,
        count(*) filter (
            where case funnel_steps.funnel_step
                when 1 then lead_stages.reached_step_1
                when 2 then lead_stages.reached_step_2
                when 3 then lead_stages.reached_step_3
                when 4 then lead_stages.reached_step_4
                when 5 then lead_stages.reached_step_5
                when 6 then lead_stages.reached_step_6
            end
        ) as lead_count
    from lead_stages
    cross join funnel_steps
    group by
        lead_stages.lead_month,
        funnel_steps.funnel_step,
        funnel_steps.kpi_name

),

with_previous as (

    select
        *,
        lag(lead_count) over (
            partition by lead_month
            order by funnel_step
        ) as previous_lead_count
    from step_counts

),

final as (

    select
        cast(lead_month as date)            as "month",
        cast(kpi_name as varchar)           as kpi_name,
        cast(funnel_step as integer)        as funnel_step,
        cast(lead_count as integer)         as "count",
        -- null for step 1, and when the previous step is 0
        cast(
            {{ conversion_pct('lead_count', 'previous_lead_count') }}
            as decimal(5, 1)
        )                                   as conversion_from_previous_pct
    from with_previous

)

select * from final
order by "month", funnel_step
