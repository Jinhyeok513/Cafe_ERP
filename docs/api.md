# Operations API

## Purpose

The FastAPI service exposes verified PostgreSQL inventory views and controlled reorder commands without duplicating stock calculations in the frontend. All quantities retain the Product Master inventory or order unit.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[api,test]'
```

Set the PostgreSQL connection and start the service:

```bash
DATABASE_URL=postgresql://localhost/cafe_stock_manage_dev \
DATABASE_POOL_MAX_SIZE=5 \
API_HOST=127.0.0.1 \
API_PORT=8000 \
  .venv/bin/cafe-api
```

`DATABASE_URL` is required. Pool size defaults to 5, host to `127.0.0.1` and port to `8000`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Database connection and loaded scenario |
| GET | `/api/kpis` | Dashboard-level inventory and quality metrics |
| GET | `/api/inventory` | Current quantity and reorder status by product |
| GET | `/api/inventory/{product_id}/movements` | Immutable product movement history |
| GET | `/api/discrepancies` | Receiving discrepancy detail |
| GET | `/api/stocktakes/accuracy` | Daily physical-count accuracy |
| GET | `/api/reorder/recommendations` | Consumption-based supplier order recommendations |
| POST | `/api/purchase-orders/drafts` | Create a validated draft purchase order |
| GET | `/api/pos/days` | Daily sales and recipe posting status |
| GET | `/api/pos/usage` | Ingredient usage for one sales date or the latest date |
| GET | `/api/pos/menu-items` | Active menu IDs available to POS imports |
| POST | `/api/pos/import` | Validate and post a batch of daily menu totals |

Interactive OpenAPI documentation is available at `/docs`, with the raw schema at `/openapi.json`.

## Filters

`GET /api/inventory` supports `status`, `search`, `limit` and `offset`. Status is restricted to the values produced by `current_inventory_status`:

```text
NEGATIVE_STOCK
REORDER_DUE
IN_STOCK
NO_REORDER_POINT
```

Movement history supports the four ledger movement types. Receiving discrepancies can be filtered by reason and supplier. Stocktake accuracy supports inclusive `date_from` and `date_to` values; an inverted range returns HTTP 422.

All query values are passed to Psycopg as parameters. Only fixed internal SQL fragments are composed for optional filters.

Draft purchase orders accept one supplier, delivery date, operator and one or more positive product quantities. Products are checked against the Product Master, must be active, and must belong to the selected supplier. The API always derives `order_unit` from Product Master rather than trusting client input.

POS imports accept daily menu totals as JSON after the web client parses the CSV. The batch is transactional: all menu IDs and recipes are checked first, duplicate date/menu totals are skipped, and each inserted sale calls the idempotent recipe posting function. The response separates received, inserted and skipped rows and reports the number of immutable `USE` movements created.

## Error behavior

- Unknown product movement history returns HTTP 404.
- Invalid enum, date or pagination input returns HTTP 422.
- PostgreSQL driver errors return HTTP 503 without exposing database details.
- A missing `DATABASE_URL` prevents application startup.

## Test

```bash
.venv/bin/python -m unittest discover -s tests -v
```

API unit tests use an injected repository, so they do not require PostgreSQL. Integration verification should additionally start a migrated database, load a dataset and request each endpoint using the real connection pool.
