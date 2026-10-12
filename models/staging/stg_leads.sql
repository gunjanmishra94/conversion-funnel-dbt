-- stg_leads: one row per valid lead.
--
-- Steps
--   1. Remove soft-deleted leads.
--   2. Remove leads whose created_date is in the future.
--   3. Keep one row per id.
--   4. Cast converted_date from text to date.
--   5. Rename columns to lowercase names without the __C suffix.
--
-- Decisions
--   * "Future" means later than the run date. Such rows would add cohort
--     months that do not exist. A row dated in the future is accepted once
--     that date has passed.
--   * When an id occurs more than once, the row with the earliest
--     created_date is kept. The copies differ only in created_date;
--     last_modified_date is identical, so it cannot break the tie.
--   * is_converted is taken as delivered, even when
--     converted_opportunity_id is empty. The assignment defines
--     "Lead Converted" by the flag alone.
--   * substatus 'Duplicate' does not mark duplicate records, so it is not
--     used for de-duplication.

with source as (

    select * from {{ source('assignment', 'LEAD') }}

),

-- steps 1 and 2
valid as (

    select *
    from source
    where
        not is_deleted
        and cast(created_date as date) <= current_date

),

-- step 3
deduplicated as (

    select *
    from valid
    qualify row_number() over (partition by id order by created_date) = 1

),

-- steps 4 and 5
renamed as (

    select
        id                                  as lead_id,
        status                              as lead_status,
        substatus__c                        as lead_substatus,
        is_converted                        as is_converted,
        cast(converted_date as date)        as converted_date,
        converted_opportunity_id            as converted_opportunity_id,
        converted_account_id                as converted_account_id,
        lead_source                         as lead_source,
        brand__c                            as brand,
        utm_source__c                       as utm_source,
        utm_medium__c                       as utm_medium,
        utm_campaign__c                     as utm_campaign,
        created_date                        as created_at,
        last_modified_date                  as last_modified_at
    from deduplicated

)

select * from renamed
