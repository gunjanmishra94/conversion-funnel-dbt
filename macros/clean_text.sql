{#- Trims a text value and collapses repeated whitespace to a single space.
    For free-text CRM fields before they are compared or grouped. -#}
{% macro clean_text(column) -%}
    regexp_replace(trim({{ column }}), '\s+', ' ', 'g')
{%- endmacro %}
