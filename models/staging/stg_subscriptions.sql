-- stg_subscriptions: one row per valid subscription.
--
-- Steps
--   1. Remove soft-deleted subscriptions.
--   2. Cast start_date and end_date from text to date.
--   3. Add is_active: true when the status is 'Active'.
--   4. Rename columns.
--
-- Decisions
--   * Subscriptions with an empty or unmatched lead_id are kept. Staging
--     does not join tables, and the funnel is built from leads outward, so
--     these rows never reach the report.
--   * is_active reflects the current status only. The source has no status
--     history, so a formerly active subscription cannot be identified.
--   * end_date and cancellation_reason are passed through and not used:
--     neither is consistent with the status.
--   * A lead may have several subscriptions. All rows are kept; they are
--     reduced to one result per lead in the intermediate model.

with source as (

    select * from {{ source('assignment', 'SUBSCRIPTION__C') }}

),

-- step 1
live as (

    select *
    from source
    where not is_deleted

),

-- steps 2 to 4
renamed as (

    select
        id                                  as subscription_id,
        lead__c                             as lead_id,
        patient__c                          as patient_account_id,
        status__c                           as subscription_status,
        status__c = 'Active'                as is_active,
        cast(start_date__c as date)         as start_date,
        cast(end_date__c as date)           as end_date,
        cancellation_reason__c              as cancellation_reason,
        delivery_cycle__c                   as delivery_cycle,
        brand__c                            as brand,
        created_date                        as created_at,
        last_modified_date                  as last_modified_at
    from live

)

select * from renamed
