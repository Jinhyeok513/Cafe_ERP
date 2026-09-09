# Synthetic Data Generation

## Purpose

The prototype generator validates the sales-to-ingredient-usage pipeline before a final cafe menu and recipe catalog is confirmed. It creates deterministic demo data, not employer or real cafe transaction history.

## Prototype scope

The committed configuration generates 30 days beginning on 1 April 2024. It includes:

- Australian season handling
- Weekday and weekend demand mix
- Synthetic weather effects
- A mild configurable university-break effect
- A revenue trend anchored near 2024 and 2026 targets
- Daily noise around the trend
- Integer menu sales allocated near each daily revenue target
- Recipe-derived ingredient usage in each product's inventory unit
- Consumption-driven purchase orders rounded to valid order units
- Receipts scheduled only on supplier delivery days
- Normal waste movements
- Daily clean stocktakes that reconcile to the inventory ledger
- An optional, separately generated operational-error scenario

Public holiday dates are intentionally empty until a real calendar source is selected. The university-break period in the prototype is explicitly labelled as a demo assumption.

## Assumption control

All unconfirmed menu names, prices, mix weights and recipe quantities live in `config/prototype_assumptions.json`. The generator refuses to run unless the configuration declares:

```text
assumption_status = synthetic_demo
```

Recipe units are checked against the same Product Master model used by PostgreSQL. A physical-content product uses `content_unit`; a count-based product uses `inventory_unit`.

## Outputs

Running the generator produces:

- `calendar.csv`
- `daily_summary.csv`
- `menu_items.csv`
- `recipes.csv`
- `pos_sales.csv`
- `inventory_usage.csv`
- `purchase_orders.csv`
- `purchase_order_items.csv`
- `goods_receipts.csv`
- `goods_receipt_items.csv`
- `inventory_movements.csv`
- `stocktakes.csv`
- `stocktake_items.csv`
- `scenario_events.csv` in the error scenario
- `manifest.json`

The manifest records the scenario, random seed, date range, row counts and a deterministic SHA-256 hash of the generated records.

## Scenarios

The `clean` scenario generates an operational history from calendar and sales through ordering, receiving, inventory movements and daily stocktakes. Purchase quantities respond to consumption, current stock, safety stock, pack size and the next supplier delivery gap. Bread and milk have no Sunday receipts, and Supplier C uses the configured Monday, Wednesday and Saturday schedule.

The `errors` scenario uses the same demand assumptions but applies the explicit rules in `error_injection`. The committed rules produce three short deliveries, two missing items, one wrong product and three stocktake variances. Damaged quantity remains zero. A short delivery posts only accepted stock; a missing or wrong item creates no RECEIVE movement for the ordered product.

Stocktake corrections follow the immutable-ledger rule:

```text
variance = physical_quantity - system_quantity
ADJUSTMENT quantity_change = variance
reason_code = STOCKTAKE_CORRECTION
```

Run both scenarios separately:

```bash
PYTHONPATH=src python3 -m cafe_stock_manage.synthetic \
  --config config/prototype_assumptions.json \
  --scenario clean \
  --output data/generated/prototype

PYTHONPATH=src python3 -m cafe_stock_manage.synthetic \
  --config config/prototype_assumptions.json \
  --scenario errors \
  --output data/generated/prototype-errors
```

`scenario_events.csv` is a compact audit list of every injected error and its resolution. The full goods receipt, movement and stocktake files remain the source of truth for balance calculations.
