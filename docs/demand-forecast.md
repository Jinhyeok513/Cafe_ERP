# Demand Forecast

## Sales baseline

The first forecasting version is intentionally transparent and appropriate for the 30-day prototype history. It averages sales by weekday across the latest 28 days, then applies the ratio between the latest seven days and the preceding seven days. The trend factor is capped between `0.85` and `1.15` so a short history cannot create extreme projections.

Observed weekday revenue variation supplies the displayed lower and upper range. The API exposes up to 30 future dates beginning after the last loaded POS day.

## Inventory depletion

For every product, the model combines:

- Average recipe-derived POS usage across the latest 14 activity days
- Average recorded waste across the same period
- Current ledger quantity
- Open purchase-order quantity
- Supplier lead time

It reports days of cover, projected stock after seven and 14 days, an expected stockout date and one of these risk states: `STOCKOUT`, `CRITICAL`, `WATCH`, `HEALTHY`, or `NO_USAGE`.

## Upgrade path

The weekday baseline is not presented as a production machine-learning model. Once sufficient real history exists, it can be evaluated against time-series alternatives using rolling backtests and forecast-error metrics while preserving the same API contract.
