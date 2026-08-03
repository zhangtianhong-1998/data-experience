{{ config(materialized = 'table') }}

with days as (
  {{ dbt.date_spine(
      'day',
      "make_date(2026, 1, 1)",
      "make_date(2027, 1, 1)"
  ) }}
)

select cast(date_day as date) as date_day
from days
where date_day >= DATE '2026-01-01'
  and date_day < DATE '2027-01-01'

