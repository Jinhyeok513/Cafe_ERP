# Cafe Stock Manage

Cafe Stock Manage is a cafe inventory operations system built around an immutable inventory ledger. It tracks purchasing, receiving, stock usage, waste, physical stocktakes and reconciliation before adding replenishment and forecasting.

## Current implementation

- Product Master with separate stock-count and physical-content units
- Supplier, purchase order and goods receipt tables
- Signed inventory movement ledger
- Goods receipt posting based on accepted quantity
- Current inventory balance view
- Daily stocktake capture and reconciliation
- Idempotent receipt and stocktake posting
- SQL flow test covering short delivery, usage and stocktake adjustment

The next data-model step is `menu_items` and `recipes`, followed by `pos_sales`.

## Inventory unit model

Inventory is stored in the unit used by the manager during a stock check. Physical volume or weight remains available for recipe conversion.

| Product | Inventory unit | Order unit | Pack size | Physical content |
|---|---:|---:|---:|---:|
| Full Cream Milk | bottle | bottle | 1 | 1.5 litre per bottle |
| Oat Milk | carton | carton | 1 | 1 litre per carton |
| Regular Coffee Beans | bag | bag | 1 | 1 kilogram per bag |
| Eggs | each | tray | 25 | Not required |

For example, receiving 9 egg trays creates a `+225 each` movement. Receiving 6 oat milk cartons creates a `+6 carton` movement. Recipe conversion can later record fractional usage such as `-2.4 carton`.

## Database setup

The SQL targets PostgreSQL.

```bash
createdb cafe_stock_manage_dev
psql -v ON_ERROR_STOP=1 -d cafe_stock_manage_dev -f db/migrations/001_core_tables.sql
psql -v ON_ERROR_STOP=1 -d cafe_stock_manage_dev -f db/migrations/002_inventory_movements.sql
psql -v ON_ERROR_STOP=1 -d cafe_stock_manage_dev -f db/migrations/003_stocktakes.sql
psql -v ON_ERROR_STOP=1 -d cafe_stock_manage_dev -f db/seeds/001_reference_data.sql
psql -v ON_ERROR_STOP=1 -d cafe_stock_manage_dev -f db/tests/001_inventory_and_stocktake_flow.sql
```

The test runs inside a transaction and rolls back its test records.

## Design notes

See [Inventory ledger and stocktake design](docs/inventory-ledger.md) for the movement rules and reconciliation flow.
