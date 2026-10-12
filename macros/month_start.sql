{#- First day of the month of a date or timestamp, as a date.
    Used for the cohort month of a lead. -#}
{% macro month_start(column) -%}
    cast(date_trunc('month', {{ column }}) as date)
{%- endmacro %}
