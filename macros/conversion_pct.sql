{#- numerator / denominator * 100, rounded.
    Null when the denominator is null or 0. -#}
{% macro conversion_pct(numerator, denominator, decimals=1) -%}
    round({{ numerator }} * 100.0 / nullif({{ denominator }}, 0), {{ decimals }})
{%- endmacro %}
