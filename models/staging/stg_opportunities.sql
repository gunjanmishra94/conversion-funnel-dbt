-- stg_opportunities: one row per valid opportunity.
--
-- Steps
--   1. Remove soft-deleted opportunities.
--   2. Clean stage_name: trim it and collapse repeated spaces.
--   3. Write every case variant of 'closed won' as 'Closed Won'.
--   4. Add is_closed_won.
--   5. Rename columns.
--
-- Decisions
--   * stage_name is free text in the CRM and contains case and whitespace
--     variants of 'Closed Won'. An exact match on the raw column would miss
--     them, so the value is normalised here. The other stages have no
--     variants and are only trimmed.
--   * The text is corrected instead of using the CRM's is_won flag, because
--     the assignment defines "Opportunity Won" by stage_name.
--   * A lead may have several opportunities. All rows are kept; they are
--     reduced to one result per lead in the intermediate model.

with source as (

    select * from {{ source('assignment', 'OPPORTUNITY') }}

),

-- steps 1 and 2
live as (

    select
        *,
        {{ clean_text('stage_name') }} as stage_name_trimmed
    from source
    where not is_deleted

),

-- steps 3 to 5
renamed as (

    select
        id                                  as opportunity_id,
        lead__c                             as lead_id,
        account_id                          as account_id,
        case
            when lower(stage_name_trimmed) = 'closed won' then 'Closed Won'
            else stage_name_trimmed
        end                                 as stage_name,
        lower(stage_name_trimmed) = 'closed won' as is_closed_won,
        is_won                              as is_won,
        is_closed                           as is_closed,
        brand__c                            as brand,
        created_date                        as created_at,
        last_stage_change_date              as last_stage_change_at,
        last_modified_date                  as last_modified_at
    from live

)

select * from renamed
