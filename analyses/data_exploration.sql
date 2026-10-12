-- Data exploration queries behind data-exploration-report.md.
-- Run against data/interview_assignment.duckdb, schema `assignment`.

-- Columns and types of the five source tables
select table_name, column_name, data_type
from information_schema.columns
where table_schema = 'assignment'
order by table_name, ordinal_position;

-- Row counts
select 'LEAD' as table_name, count(*) as row_count from assignment.LEAD
union all select 'OPPORTUNITY', count(*) from assignment.OPPORTUNITY
union all select 'SUBSCRIPTION__C', count(*) from assignment.SUBSCRIPTION__C
union all select 'DELIVERY__C', count(*) from assignment.DELIVERY__C
union all select 'ACCOUNT', count(*) from assignment.ACCOUNT;

-- ID uniqueness and nulls (repeat per table)
select
    count(*) as row_count,
    count(distinct ID) as distinct_ids,
    count(*) - count(ID) as null_ids
from assignment.LEAD;

-- Duplicate lead IDs and the columns that differ within a pair
with dup as (
    select ID from assignment.LEAD group by ID having count(*) > 1
)

select
    l.ID,
    count(*) as row_count,
    count(distinct l.CREATED_DATE) as created_dates,
    count(distinct date_trunc('month', l.CREATED_DATE)) as created_months,
    count(distinct l.STATUS) as statuses,
    count(distinct l.IS_CONVERTED) as converted_flags,
    count(distinct l.LAST_MODIFIED_DATE) as last_modified_dates
from assignment.LEAD as l
inner join dup on l.ID = dup.ID
group by l.ID;

-- Deleted rows per table
select 'LEAD' as table_name, count(*) as deleted_rows from assignment.LEAD where IS_DELETED
union all select 'OPPORTUNITY', count(*) from assignment.OPPORTUNITY where IS_DELETED
union all select 'SUBSCRIPTION__C', count(*) from assignment.SUBSCRIPTION__C where IS_DELETED
union all select 'DELIVERY__C', count(*) from assignment.DELIVERY__C where IS_DELETED
union all select 'ACCOUNT', count(*) from assignment.ACCOUNT where IS_DELETED;

-- Child rows against the state of their parent (orphans, deleted parents)
with lead_state as (
    select ID, bool_or(IS_DELETED) as is_deleted from assignment.LEAD group by ID
)

select
    'OPPORTUNITY -> LEAD' as relationship,
    o.IS_DELETED as child_deleted,
    case
        when ls.ID is null then 'orphan'
        when ls.is_deleted then 'parent deleted'
        else 'ok'
    end as parent_state,
    count(*) as row_count
from assignment.OPPORTUNITY as o
left join lead_state as ls on o.LEAD__C = ls.ID
group by all

union all

select
    'SUBSCRIPTION__C -> LEAD',
    s.IS_DELETED,
    case
        when s.LEAD__C is null then 'null key'
        when ls.ID is null then 'orphan'
        when ls.is_deleted then 'parent deleted'
        else 'ok'
    end,
    count(*)
from assignment.SUBSCRIPTION__C as s
left join lead_state as ls on s.LEAD__C = ls.ID
group by all

union all

select
    'DELIVERY__C -> SUBSCRIPTION__C',
    d.IS_DELETED,
    case
        when s.ID is null then 'orphan'
        when s.IS_DELETED then 'parent deleted'
        else 'ok'
    end,
    count(*)
from assignment.DELIVERY__C as d
left join assignment.SUBSCRIPTION__C as s on d.SUBSCRIPTION__C = s.ID
group by all
order by 1, 2, 3;

-- Distinct values of the status and category columns (repeat per column)
select STAGE_NAME, count(*) as row_count
from assignment.OPPORTUNITY
group by STAGE_NAME
order by row_count desc;

-- Spelling, case and whitespace variants of 'Closed Won'
select ID, '[' || STAGE_NAME || ']' as stage_name_raw, IS_WON, IS_CLOSED, IS_DELETED
from assignment.OPPORTUNITY
where STAGE_NAME <> 'Closed Won'
    and lower(regexp_replace(trim(STAGE_NAME), '\s+', ' ', 'g')) = 'closed won';

-- Delivery statuses, by status of the subscription they belong to
select
    s.STATUS__C as subscription_status,
    d.STATUS__C as delivery_status,
    count(*) as deliveries,
    count(distinct s.ID) as subscriptions
from assignment.DELIVERY__C as d
inner join assignment.SUBSCRIPTION__C as s on d.SUBSCRIPTION__C = s.ID
group by all
order by 1, 2;

-- LEAD.IS_CONVERTED against the conversion fields, and against STATUS
select
    IS_CONVERTED,
    CONVERTED_OPPORTUNITY_ID is not null as has_opportunity_id,
    CONVERTED_ACCOUNT_ID is not null as has_account_id,
    CONVERTED_DATE is not null as has_converted_date,
    count(*) as row_count
from assignment.LEAD
group by all
order by 1, 2, 3, 4;

select STATUS, IS_CONVERTED, count(*) as row_count
from assignment.LEAD
group by all
order by 1, 2;

-- OPPORTUNITY.IS_WON and IS_CLOSED against the normalised stage
select
    lower(regexp_replace(trim(STAGE_NAME), '\s+', ' ', 'g')) as stage_normalised,
    IS_WON,
    IS_CLOSED,
    count(*) as row_count
from assignment.OPPORTUNITY
group by all
order by 1, 2, 3;

-- Subscription status against end date and cancellation reason
select
    STATUS__C,
    END_DATE__C is not null as has_end_date,
    CANCELLATION_REASON__C is not null as has_cancellation_reason,
    count(*) as row_count
from assignment.SUBSCRIPTION__C
group by all
order by 1, 2, 3;

-- Date ranges, and leads per creation month
select
    min(CREATED_DATE) as min_created,
    max(CREATED_DATE) as max_created
from assignment.LEAD;

select date_trunc('month', CREATED_DATE)::date as lead_month, count(*) as lead_rows
from assignment.LEAD
group by 1
order by 1;

-- Future-dated leads, and the format of dates stored as text
select ID, CREATED_DATE, STATUS, IS_CONVERTED, CONVERTED_OPPORTUNITY_ID
from assignment.LEAD
where CREATED_DATE > (select max(CREATED_DATE) from assignment.DELIVERY__C);

select regexp_replace(START_DATE__C, '[0-9]', '9', 'g') as date_format, count(*) as row_count
from assignment.SUBSCRIPTION__C
group by 1;

-- Date order problems
select 'subscription end before start' as check_name, count(*) as row_count
from assignment.SUBSCRIPTION__C
where END_DATE__C::date < START_DATE__C::date

union all

select 'subscription start before record creation', count(*)
from assignment.SUBSCRIPTION__C
where START_DATE__C::date < CREATED_DATE::date

union all

select 'opportunity stage change before creation', count(*)
from assignment.OPPORTUNITY
where LAST_STAGE_CHANGE_DATE < CREATED_DATE

union all

select 'opportunity created before its lead', count(*)
from assignment.OPPORTUNITY as o
inner join (select ID, min(CREATED_DATE) as created_date from assignment.LEAD group by ID) as l
    on o.LEAD__C = l.ID
where o.CREATED_DATE < l.created_date

union all

select 'subscription created before its lead', count(*)
from assignment.SUBSCRIPTION__C as s
inner join (select ID, min(CREATED_DATE) as created_date from assignment.LEAD group by ID) as l
    on s.LEAD__C = l.ID
where s.CREATED_DATE < l.created_date

union all

select 'delivery created before its subscription', count(*)
from assignment.DELIVERY__C as d
inner join assignment.SUBSCRIPTION__C as s on d.SUBSCRIPTION__C = s.ID
where d.CREATED_DATE < s.CREATED_DATE;

-- Brand agreement between a lead and its child records
with lead_brand as (
    select ID, min(BRAND__C) as brand from assignment.LEAD group by ID
)

select
    'OPPORTUNITY vs LEAD' as comparison,
    count(*) filter (where o.BRAND__C <> lb.brand) as mismatches,
    count(*) as compared
from assignment.OPPORTUNITY as o
inner join lead_brand as lb on o.LEAD__C = lb.ID

union all

select
    'SUBSCRIPTION__C vs LEAD',
    count(*) filter (where s.BRAND__C <> lb.brand),
    count(*)
from assignment.SUBSCRIPTION__C as s
inner join lead_brand as lb on s.LEAD__C = lb.ID

union all

select
    'DELIVERY__C vs SUBSCRIPTION__C',
    count(*) filter (where d.BRAND__C <> s.BRAND__C),
    count(*)
from assignment.DELIVERY__C as d
inner join assignment.SUBSCRIPTION__C as s on d.SUBSCRIPTION__C = s.ID;

-- More than one opportunity or subscription per lead
select 'opportunities' as child, per_lead, count(*) as leads
from (select LEAD__C, count(*) as per_lead from assignment.OPPORTUNITY group by LEAD__C)
group by all

union all

select 'subscriptions', per_lead, count(*)
from (
    select LEAD__C, count(*) as per_lead
    from assignment.SUBSCRIPTION__C
    where LEAD__C is not null
    group by LEAD__C
)
group by all
order by 1, 2;

-- ---------------------------------------------------------------------------
-- Relationships between the tables
-- ---------------------------------------------------------------------------

-- Null keys and orphans for each link (shown for two links, repeat per link)
select
    'OPPORTUNITY.LEAD__C -> LEAD.ID' as link,
    count(*) as child_rows,
    count(*) filter (where o.LEAD__C is null) as null_keys,
    count(*) filter (where o.LEAD__C is not null and l.ID is null) as orphans
from assignment.OPPORTUNITY as o
left join (select distinct ID from assignment.LEAD) as l on o.LEAD__C = l.ID

union all

select
    'SUBSCRIPTION__C.LEAD__C -> LEAD.ID',
    count(*),
    count(*) filter (where s.LEAD__C is null),
    count(*) filter (where s.LEAD__C is not null and l.ID is null)
from assignment.SUBSCRIPTION__C as s
left join (select distinct ID from assignment.LEAD) as l on s.LEAD__C = l.ID;

-- Opportunities and subscriptions per live, de-duplicated lead
with live_leads as (
    select distinct ID from assignment.LEAD where not IS_DELETED
),

opportunities as (
    select LEAD__C, count(*) as per_lead
    from assignment.OPPORTUNITY
    where not IS_DELETED
    group by LEAD__C
),

subscriptions as (
    select LEAD__C, count(*) as per_lead
    from assignment.SUBSCRIPTION__C
    where not IS_DELETED
    group by LEAD__C
)

select 'opportunities' as child, coalesce(o.per_lead, 0) as per_lead, count(*) as leads
from live_leads as l
left join opportunities as o on l.ID = o.LEAD__C
group by all

union all

select 'subscriptions', coalesce(s.per_lead, 0), count(*)
from live_leads as l
left join subscriptions as s on l.ID = s.LEAD__C
group by all
order by 1, 2;

-- The two paths from a lead to an opportunity, compared per lead
with live_leads as (
    select distinct on (ID) * from assignment.LEAD where not IS_DELETED
),

via_foreign_key as (
    select LEAD__C, list(ID) as opportunity_ids, count(*) as opportunities
    from assignment.OPPORTUNITY
    where not IS_DELETED
    group by LEAD__C
)

select
    case
        when l.CONVERTED_OPPORTUNITY_ID is null then 'no converted id'
        when c.ID is null then 'converted id matches no opportunity'
        else 'converted id ok'
    end as path_converted_id,
    coalesce(v.opportunities, 0) as opportunities_via_lead_key,
    list_contains(v.opportunity_ids, l.CONVERTED_OPPORTUNITY_ID) as converted_id_among_them,
    l.IS_CONVERTED,
    count(*) as leads
from live_leads as l
left join assignment.OPPORTUNITY as c on l.CONVERTED_OPPORTUNITY_ID = c.ID
left join via_foreign_key as v on l.ID = v.LEAD__C
group by all
order by 1, 2, 3, 4;

-- Leads with a won opportunity, by path
with live_leads as (
    select distinct on (ID) * from assignment.LEAD where not IS_DELETED
),

live_opportunities as (
    select
        *,
        lower(regexp_replace(trim(STAGE_NAME), '\s+', ' ', 'g')) = 'closed won' as is_closed_won
    from assignment.OPPORTUNITY
    where not IS_DELETED
)

select
    count(*) filter (
        where exists (
            select 1 from live_opportunities as o
            where o.ID = l.CONVERTED_OPPORTUNITY_ID and o.is_closed_won
        )
    ) as won_via_converted_id,
    count(*) filter (
        where exists (
            select 1 from live_opportunities as o
            where o.LEAD__C = l.ID and o.is_closed_won
        )
    ) as won_via_lead_key
from live_leads as l;

-- ---------------------------------------------------------------------------
-- Funnel semantics
-- ---------------------------------------------------------------------------

-- One row per cleaned lead with a flag per stage, then both funnels.
-- Cleaning applied: deleted rows removed, one row per lead ID (earliest),
-- future-dated leads removed, stage name normalised.
with leads as (
    select distinct on (ID) *
    from assignment.LEAD
    where not IS_DELETED
    order by ID, CREATED_DATE
),

opportunities as (
    select * from assignment.OPPORTUNITY where not IS_DELETED
),

subscriptions as (
    select * from assignment.SUBSCRIPTION__C where not IS_DELETED
),

deliveries as (
    select * from assignment.DELIVERY__C where not IS_DELETED
),

lead_flags as (
    select
        l.ID as lead_id,
        date_trunc('month', l.CREATED_DATE)::date as lead_month,
        l.STATUS = 'Qualified' as is_qualified,
        l.IS_CONVERTED as is_converted,
        exists (
            select 1 from opportunities as o
            where o.LEAD__C = l.ID
                and lower(regexp_replace(trim(o.STAGE_NAME), '\s+', ' ', 'g')) = 'closed won'
        ) as has_won_opportunity,
        exists (
            select 1 from subscriptions as s
            where s.LEAD__C = l.ID and s.STATUS__C = 'Active'
        ) as has_active_subscription,
        exists (
            select 1
            from subscriptions as s
            inner join deliveries as d on s.ID = d.SUBSCRIPTION__C
            where s.LEAD__C = l.ID and s.STATUS__C = 'Active'
        ) as has_delivery
    from leads as l
    where l.CREATED_DATE <= (select max(CREATED_DATE) from deliveries)
)

select
    lead_month,
    count(*) as lead_created,
    count(*) filter (where is_qualified) as qualified,
    -- independent count: each stage by its own condition
    count(*) filter (where is_converted) as converted_independent,
    count(*) filter (where has_won_opportunity) as won_independent,
    count(*) filter (where has_active_subscription) as active_independent,
    count(*) filter (where has_delivery) as delivery_independent,
    -- strict sequence: each stage also requires every earlier stage
    count(*) filter (where is_qualified and is_converted) as converted_strict,
    count(*) filter (
        where is_qualified and is_converted and has_won_opportunity
    ) as won_strict,
    count(*) filter (
        where is_qualified and is_converted and has_won_opportunity and has_active_subscription
    ) as active_strict,
    count(*) filter (
        where is_qualified and is_converted and has_won_opportunity
            and has_active_subscription and has_delivery
    ) as delivery_strict
from lead_flags
group by lead_month
order by lead_month;
