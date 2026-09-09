# PostgreSQL Dataset Import

## Purpose

The dataset loader moves a generated `clean` or `errors` scenario into the operational PostgreSQL schema without bypassing relational constraints. Stable source keys connect CSV records to database identity keys and allow the loader to detect repeated imports.

## Prerequisites

Apply migrations in numeric order and then load the reference seed:

```bash
createdb cafe_stock_manage_dev
psql -v ON_ERROR_STOP=1 -d cafe_stock_manage_dev -f db/migrations/001_core_tables.sql
psql -v ON_ERROR_STOP=1 -d cafe_stock_manage_dev -f db/migrations/002_inventory_movements.sql
psql -v ON_ERROR_STOP=1 -d cafe_stock_manage_dev -f db/migrations/003_stocktakes.sql
psql -v ON_ERROR_STOP=1 -d cafe_stock_manage_dev -f db/migrations/004_menu_recipes_pos.sql
psql -v ON_ERROR_STOP=1 -d cafe_stock_manage_dev -f db/migrations/005_dataset_import_and_quality.sql
psql -v ON_ERROR_STOP=1 -d cafe_stock_manage_dev -f db/migrations/006_reorder_planning.sql
psql -v ON_ERROR_STOP=1 -d cafe_stock_manage_dev -f db/seeds/001_reference_data.sql
```

## Load a scenario

```bash
PYTHONPATH=src python3 -m cafe_stock_manage.db_loader \
  data/generated/prototype-errors \
  --database-url cafe_stock_manage_dev
```

`DATABASE_URL` can be used instead of `--database-url`. The value may be a database name or a PostgreSQL connection URI.

Before loading, the command checks:

- Required files and exact column order
- Per-file SHA-256 checksums
- CSV row counts
- Manifest scenario and metadata
- Whether the database already contains a different operational dataset

The same dataset hash is idempotent and returns without inserting duplicates. A different dataset is rejected while operational data exists. To intentionally switch between the clean and error scenarios, use:

```bash
PYTHONPATH=src python3 -m cafe_stock_manage.db_loader \
  data/generated/prototype \
  --database-url cafe_stock_manage_dev \
  --reset
```

`--reset` truncates transactional inventory data and import history. Product, supplier, menu and recipe master data remain available and are updated from the incoming scenario where applicable.

## Transaction and quality gate

CSV files first enter temporary text staging tables. PostgreSQL then converts and inserts them in dependency order. Any type conversion, foreign key, quantity constraint or source mapping failure rolls back the entire import.

Before commit, `data_quality_issues` must return zero rows. It currently checks:

- Negative current inventory
- Accepted receipt quantity against RECEIVE movements
- Stocktake variance against ADJUSTMENT movements
- Recipe-derived POS usage against USE movements

Run the read-only integration assertion after loading:

```bash
psql -v ON_ERROR_STOP=1 -d cafe_stock_manage_dev \
  -f db/tests/003_loaded_dataset_validation.sql
```

## Operational views

```sql
SELECT * FROM current_inventory_status ORDER BY stock_status, product_id;
SELECT * FROM receiving_discrepancy_summary ORDER BY supplier_id, discrepancy_reason;
SELECT * FROM stocktake_accuracy_daily ORDER BY stocktake_date;
SELECT * FROM data_quality_issues;
SELECT * FROM reorder_recommendations ORDER BY urgency, expected_delivery_date;
```

`inventory_movement_timeline` exposes the signed movement and running quantity for every product. It is the database source for movement history and future dashboard charts.
