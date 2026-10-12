-- stg_deliveries: one row per valid delivery.
--
-- Steps
--   1. Remove soft-deleted deliveries.
--   2. Rename columns.
--
-- Decisions
--   * Deliveries with an unmatched subscription_id are kept. Staging does
--     not join tables, and these rows never reach a lead.
--   * Delivery status is not filtered: 'Cancelled' and 'Returned' rows are
--     kept. In the source, every subscription with a delivery has at least
--     one 'Delivered', so a filter would not change "First Delivery".
--   * A subscription may have several deliveries. All rows are kept; the
--     funnel only tests whether at least one exists.

with source as (

    select * from {{ source('assignment', 'DELIVERY__C') }}

),

-- step 1
live as (

    select *
    from source
    where not is_deleted

),

-- step 2
renamed as (

    select
        id                                  as delivery_id,
        subscription__c                     as subscription_id,
        status__c                           as delivery_status,
        brand__c                            as brand,
        created_date                        as created_at
    from live

)

select * from renamed
