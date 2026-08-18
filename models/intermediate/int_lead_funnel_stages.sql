-- One row per lead: its cohort month and how far it got in the funnel.
--
-- is_* / has_* are the stage conditions taken on their own.
-- reached_step_N is the strict version (needs every earlier step too),
-- and that is what the report counts. Both are kept so we can see how many
-- leads skip a step.

with leads as (

    select * from {{ ref('stg_leads') }}

),

opportunities as (

    select * from {{ ref('stg_opportunities') }}

),

subscriptions as (

    select * from {{ ref('stg_subscriptions') }}

),

deliveries as (

    select * from {{ ref('stg_deliveries') }}

),

-- a lead can have more than one opportunity or subscription,
-- so each of these is reduced to one row per lead before joining

won_opportunities as (

    select lead_id
    from opportunities
    where is_closed_won
    group by lead_id

),

active_subscriptions as (

    select lead_id
    from subscriptions
    where is_active
    group by lead_id

),

-- the delivery has to be on an active subscription
delivered_subscriptions as (

    select subscriptions.lead_id
    from subscriptions
    inner join deliveries
        on subscriptions.subscription_id = deliveries.subscription_id
    where subscriptions.is_active
    group by subscriptions.lead_id

),

stage_conditions as (

    select
        leads.lead_id,
        {{ month_start('leads.created_at') }}                 as lead_month,
        leads.created_at,
        leads.brand,
        leads.lead_source,
        leads.utm_source,
        leads.utm_medium,
        leads.utm_campaign,
        leads.lead_status = 'Qualified'                     as is_qualified,
        leads.is_converted,
        won_opportunities.lead_id is not null               as has_won_opportunity,
        active_subscriptions.lead_id is not null            as has_active_subscription,
        delivered_subscriptions.lead_id is not null         as has_delivery
    from leads
    left join won_opportunities
        on leads.lead_id = won_opportunities.lead_id
    left join active_subscriptions
        on leads.lead_id = active_subscriptions.lead_id
    left join delivered_subscriptions
        on leads.lead_id = delivered_subscriptions.lead_id

),

strict_sequence as (

    select
        *,
        true                                                as reached_step_1,
        is_qualified                                        as reached_step_2,
        is_qualified and is_converted                       as reached_step_3,
        is_qualified and is_converted and has_won_opportunity
                                                            as reached_step_4,
        is_qualified and is_converted and has_won_opportunity
        and has_active_subscription                         as reached_step_5,
        is_qualified and is_converted and has_won_opportunity
        and has_active_subscription and has_delivery        as reached_step_6
    from stage_conditions

),

final as (

    select
        *,
        -- false if the lead hits a stage without the ones before it
        (
            (reached_step_3 = is_converted)
            and (reached_step_4 = has_won_opportunity)
            and (reached_step_5 = has_active_subscription)
            and (reached_step_6 = has_delivery)
        )                                                   as is_stage_consistent
    from strict_sequence

)

select * from final
