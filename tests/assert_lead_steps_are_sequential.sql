-- Same rule at lead level: a lead that reached step N reached every step
-- before it.

select *
from {{ ref('int_lead_funnel_stages') }}
where (reached_step_2 and not reached_step_1)
    or (reached_step_3 and not reached_step_2)
    or (reached_step_4 and not reached_step_3)
    or (reached_step_5 and not reached_step_4)
    or (reached_step_6 and not reached_step_5)
