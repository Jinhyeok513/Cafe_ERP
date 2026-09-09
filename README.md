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
- Menu Item and Recipe/BOM tables with unit validation
- Daily POS sales and recipe-derived inventory usage posting
- Protection against duplicate posting and edits to posted sales
- Deterministic synthetic calendar, revenue, POS and ingredient-usage generator
- Configurable demo assumptions with seed and output manifest
- Consumption-driven orders, scheduled receipts, waste and daily stocktakes
- Separate deterministic error scenario for receiving and stocktake reconciliation
- Transactional PostgreSQL dataset loader with checksum verification
- Inventory timeline, stock status, discrepancy and stocktake quality views
- FastAPI for inventory, movement, discrepancy, stocktake and reorder operations
- Responsive Next.js operations dashboard backed by the live API
- Consumption-based reorder recommendations and draft purchase-order creation

The agreed operational data-model steps are implemented through `pos_sales`. Synthetic generation covers the clean operational flow and a separately generated error scenario with short deliveries, missing items, wrong products and stocktake corrections. Actual menu names, selling prices and recipe quantities remain TBD and are not included as production seed data.

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
psql -v ON_ERROR_STOP=1 -d cafe_stock_manage_dev -f db/migrations/004_menu_recipes_pos.sql
psql -v ON_ERROR_STOP=1 -d cafe_stock_manage_dev -f db/migrations/005_dataset_import_and_quality.sql
psql -v ON_ERROR_STOP=1 -d cafe_stock_manage_dev -f db/migrations/006_reorder_planning.sql
psql -v ON_ERROR_STOP=1 -d cafe_stock_manage_dev -f db/seeds/001_reference_data.sql
psql -v ON_ERROR_STOP=1 -d cafe_stock_manage_dev -f db/tests/001_inventory_and_stocktake_flow.sql
psql -v ON_ERROR_STOP=1 -d cafe_stock_manage_dev -f db/tests/002_recipe_pos_usage_flow.sql
```

The test runs inside a transaction and rolls back its test records.

## Synthetic prototype

The prototype assumptions are explicitly synthetic and configurable. Generate the committed 30-day dataset with:

```bash
PYTHONPATH=src python3 -m cafe_stock_manage.synthetic \
  --config config/prototype_assumptions.json \
  --scenario clean \
  --output data/generated/prototype
```

Generate the matching operational-error dataset with:

```bash
PYTHONPATH=src python3 -m cafe_stock_manage.synthetic \
  --config config/prototype_assumptions.json \
  --scenario errors \
  --output data/generated/prototype-errors
```

Load a generated dataset after applying the migrations and seed data:

```bash
PYTHONPATH=src python3 -m cafe_stock_manage.db_loader \
  data/generated/prototype-errors \
  --database-url cafe_stock_manage_dev
```

The loader verifies every CSV checksum and row count, then imports all operational records in one transaction. It returns successfully without duplicating rows when the same dataset is already loaded. Use `--reset` only when intentionally replacing the current operational dataset with another scenario.

Run the generator unit tests with:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Operations API

Install the API and test dependencies in a virtual environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[api,test]'
```

Start the API against a migrated and loaded PostgreSQL database:

```bash
DATABASE_URL=postgresql://localhost/cafe_stock_manage_dev \
  .venv/bin/cafe-api
```

The service exposes interactive OpenAPI documentation at `http://127.0.0.1:8000/docs`. Operational endpoints are under `/api`, including current inventory, product movements, receiving discrepancies, stocktake accuracy, dashboard KPIs, reorder recommendations and draft purchase-order creation.

## Operations dashboard

Install and run the Next.js dashboard in a second terminal after the API is available:

```bash
cd apps/web
pnpm install
CAFE_API_URL=http://127.0.0.1:8000 pnpm dev
```

Open `http://127.0.0.1:3000` to view live inventory balances, reorder alerts, receiving exceptions and stocktake accuracy. Reorder planning is available at `/reorder`; it calculates recommendations in stock units and creates supplier purchase orders in `DRAFT` status. The dashboard performs server-side API requests and does not expose database credentials to the browser.

## Design notes

See [Inventory ledger and stocktake design](docs/inventory-ledger.md) for movement and reconciliation rules, [Menu Recipe and POS Usage Design](docs/menu-recipe-pos.md) for recipe conversion and POS posting, [Synthetic Data Generation](docs/synthetic-data.md) for the configurable prototype, [PostgreSQL Dataset Import](docs/database-import.md) for loading and quality checks, [Reorder Planning](docs/reorder-planning.md) for replenishment calculations, and [Operations API](docs/api.md) for the HTTP contract.
