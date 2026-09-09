# Reorder Planning

## Calculation

The `reorder_recommendations` view uses the last 14 activity days as its demand window. `USE` and `WASTE` movements both contribute to average daily consumption.

```text
projected_on_delivery
= current_quantity + on_order_quantity - average_daily_usage * lead_time_days

target_inventory
= average_daily_usage * (lead_time_days + review_period_days) + safety_stock

recommended_order_quantity
= ceil((target_inventory - projected_on_delivery) / pack_size)
```

The result is expressed in `products.order_unit`. Eggs therefore round to trays while milk and coffee round to bottles, cartons, or bags. Open draft and future submitted orders are included so the same requirement is not ordered twice.

## Delivery date

The first eligible supplier delivery day on or after the lead-time date is selected. Suppliers without an explicit weekly schedule use the lead-time date directly.

## Priority

- `CRITICAL`: current inventory is negative.
- `ORDER_NOW`: current inventory is at or below its reorder point.
- `REVIEW`: projected delivery-day inventory reaches safety stock.
- `PLANNED`: demand creates a future requirement but is not yet urgent.

The API can create a purchase order in `DRAFT` status from one supplier group. Submission and external supplier transmission remain a separate approval step.
