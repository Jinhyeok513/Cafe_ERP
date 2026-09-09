# Excel Operations Report

`Cafe_ERP_Operations.xlsx` is a point-in-time operational export generated from the Cafe ERP API and PostgreSQL dataset.

## Workbook structure

| Sheet | Purpose |
|---|---|
| Summary | Formula-driven KPIs, priority orders and 14-day revenue chart |
| Reorder | Supplier delivery schedule and replenishment recommendations |
| POS Daily | Posted sales totals and usage posting status |
| Sales Forecast | Thirty-day weekday baseline, bounds and trend factors |
| Inventory Forecast | Depletion rate, incoming stock and projected risk |
| Receiving | Goods receipt discrepancies and accepted quantities |
| Stocktakes | Physical count accuracy and variance |
| Inventory | Current stock in each product's operational inventory unit |
| Ledger | Immutable signed movement history and source traceability |

Dates, numeric quantities, percentages and AUD currency are stored as native Excel values. The Summary sheet references detail-sheet formulas, and each detail sheet uses an Excel table with filters and frozen headers.

## Regeneration

The workbook in `apps/web/public/reports` is a committed portfolio snapshot. Its source data comes from the API endpoints for KPIs, inventory, reorder, POS, forecasts, receiving, stocktakes and movement history. Regenerate it after loading a new scenario, then replace the public workbook and preview together so the download and on-screen preview remain aligned.
