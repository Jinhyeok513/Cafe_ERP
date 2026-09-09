"""Validate and load a generated cafe dataset into PostgreSQL."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


REQUIRED_COLUMNS = {
    "menu_items.csv": (
        "menu_item_id",
        "menu_item_name",
        "menu_category",
        "selling_price",
        "assumption_status",
    ),
    "recipes.csv": (
        "menu_item_id",
        "product_id",
        "ingredient_quantity",
        "ingredient_unit",
        "assumption_status",
    ),
    "purchase_orders.csv": (
        "po_source_key",
        "supplier_id",
        "order_datetime",
        "expected_delivery_date",
        "order_status",
        "ordered_by",
    ),
    "purchase_order_items.csv": (
        "po_item_source_key",
        "po_source_key",
        "product_id",
        "ordered_quantity",
        "order_unit",
    ),
    "goods_receipts.csv": (
        "receipt_source_key",
        "po_source_key",
        "supplier_id",
        "received_datetime",
        "invoice_number",
        "received_by",
        "receipt_status",
    ),
    "goods_receipt_items.csv": (
        "receipt_item_source_key",
        "receipt_source_key",
        "po_item_source_key",
        "product_id",
        "invoice_quantity",
        "received_quantity",
        "damaged_quantity",
        "accepted_quantity",
        "wrong_item_flag",
        "discrepancy_reason",
    ),
    "pos_sales.csv": (
        "pos_source_key",
        "sale_date",
        "menu_item_id",
        "quantity_sold",
        "unit_price",
        "gross_revenue",
    ),
    "inventory_movements.csv": (
        "movement_source_key",
        "product_id",
        "movement_datetime",
        "movement_type",
        "quantity_change",
        "source_type",
        "source_id",
        "reason_code",
        "recorded_by",
    ),
    "stocktakes.csv": (
        "stocktake_source_key",
        "stocktake_datetime",
        "stocktake_status",
        "performed_by",
    ),
    "stocktake_items.csv": (
        "stocktake_item_source_key",
        "stocktake_source_key",
        "product_id",
        "inventory_unit",
        "physical_quantity",
        "system_quantity",
        "variance",
        "review_status",
    ),
}


class DatasetLoadError(RuntimeError):
    """Raised when a dataset cannot be validated or loaded."""


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_row_count(path: Path) -> int:
    if path.stat().st_size == 0:
        return 0
    with path.open(newline="", encoding="utf-8") as csv_file:
        return sum(1 for _ in csv.reader(csv_file)) - 1


def validate_dataset(dataset_dir: str | Path) -> dict[str, Any]:
    dataset_path = Path(dataset_dir).resolve()
    manifest_path = dataset_path / "manifest.json"
    if not manifest_path.is_file():
        raise DatasetLoadError(f"Missing manifest: {manifest_path}")

    with manifest_path.open(encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)

    if manifest.get("scenario") not in {"clean", "errors"}:
        raise DatasetLoadError("Manifest scenario must be clean or errors")
    if not isinstance(manifest.get("files"), dict):
        raise DatasetLoadError("Manifest must contain per-file checksums")

    for filename, file_manifest in manifest["files"].items():
        csv_path = dataset_path / filename
        if not csv_path.is_file():
            raise DatasetLoadError(f"Missing manifest dataset file: {filename}")
        if file_sha256(csv_path) != file_manifest.get("sha256"):
            raise DatasetLoadError(f"Checksum mismatch: {filename}")
        actual_rows = csv_row_count(csv_path)
        if actual_rows != int(file_manifest.get("rows", -1)):
            raise DatasetLoadError(f"Row count mismatch: {filename}")
        dataset_name = Path(filename).stem
        if actual_rows != int(manifest.get("row_counts", {}).get(dataset_name, -1)):
            raise DatasetLoadError(f"Manifest row counts disagree: {filename}")

    for filename, expected_columns in REQUIRED_COLUMNS.items():
        csv_path = dataset_path / filename
        file_manifest = manifest["files"].get(filename)
        if not csv_path.is_file() or file_manifest is None:
            raise DatasetLoadError(f"Missing required dataset file: {filename}")
        with csv_path.open(newline="", encoding="utf-8") as csv_file:
            header = tuple(next(csv.reader(csv_file), []))
        if header != expected_columns:
            raise DatasetLoadError(
                f"Unexpected columns in {filename}: {header}; expected {expected_columns}"
            )

    return manifest


def sql_literal(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def copy_command(table: str, path: Path) -> str:
    escaped_path = str(path.resolve()).replace("'", "''")
    return f"\\copy {table} FROM '{escaped_path}' WITH (FORMAT csv, HEADER true)"


def psql_command(connection: str) -> list[str]:
    executable = shutil.which("psql")
    if executable is None:
        raise DatasetLoadError("psql is required but was not found on PATH")
    return [
        executable,
        "--no-psqlrc",
        "--quiet",
        "--no-align",
        "--tuples-only",
        "--dbname",
        connection,
        "--set",
        "ON_ERROR_STOP=1",
    ]


def run_psql(connection: str, sql: str, capture_output: bool = True) -> str:
    result = subprocess.run(
        psql_command(connection),
        input=sql,
        text=True,
        capture_output=capture_output,
        check=False,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        raise DatasetLoadError(f"PostgreSQL command failed: {message}")
    return result.stdout.strip()


def inspect_database(connection: str) -> tuple[set[str], int]:
    sql = """
SET search_path TO cafe_stock_manage, public;
SELECT
    COALESCE(string_agg(dataset_sha256, ','), ''),
    (
        (SELECT COUNT(*) FROM purchase_orders) +
        (SELECT COUNT(*) FROM goods_receipts) +
        (SELECT COUNT(*) FROM stocktakes) +
        (SELECT COUNT(*) FROM pos_sales) +
        (SELECT COUNT(*) FROM inventory_movements)
    )
FROM dataset_imports;
"""
    output = run_psql(connection, sql)
    last_line = output.splitlines()[-1]
    hashes_text, operational_count = last_line.split("|", 1)
    hashes = {value for value in hashes_text.split(",") if value}
    return hashes, int(operational_count)


def stage_table_sql() -> str:
    return """
CREATE TEMP TABLE stage_menu_items (
    menu_item_id TEXT, menu_item_name TEXT, menu_category TEXT,
    selling_price TEXT, assumption_status TEXT
);
CREATE TEMP TABLE stage_recipes (
    menu_item_id TEXT, product_id TEXT, ingredient_quantity TEXT,
    ingredient_unit TEXT, assumption_status TEXT
);
CREATE TEMP TABLE stage_purchase_orders (
    po_source_key TEXT, supplier_id TEXT, order_datetime TEXT,
    expected_delivery_date TEXT, order_status TEXT, ordered_by TEXT
);
CREATE TEMP TABLE stage_purchase_order_items (
    po_item_source_key TEXT, po_source_key TEXT, product_id TEXT,
    ordered_quantity TEXT, order_unit TEXT
);
CREATE TEMP TABLE stage_goods_receipts (
    receipt_source_key TEXT, po_source_key TEXT, supplier_id TEXT,
    received_datetime TEXT, invoice_number TEXT, received_by TEXT,
    receipt_status TEXT
);
CREATE TEMP TABLE stage_goods_receipt_items (
    receipt_item_source_key TEXT, receipt_source_key TEXT,
    po_item_source_key TEXT, product_id TEXT, invoice_quantity TEXT,
    received_quantity TEXT, damaged_quantity TEXT, accepted_quantity TEXT,
    wrong_item_flag TEXT, discrepancy_reason TEXT
);
CREATE TEMP TABLE stage_pos_sales (
    pos_source_key TEXT, sale_date TEXT, menu_item_id TEXT,
    quantity_sold TEXT, unit_price TEXT, gross_revenue TEXT
);
CREATE TEMP TABLE stage_inventory_movements (
    movement_source_key TEXT, product_id TEXT, movement_datetime TEXT,
    movement_type TEXT, quantity_change TEXT, source_type TEXT,
    source_id TEXT, reason_code TEXT, recorded_by TEXT
);
CREATE TEMP TABLE stage_stocktakes (
    stocktake_source_key TEXT, stocktake_datetime TEXT,
    stocktake_status TEXT, performed_by TEXT
);
CREATE TEMP TABLE stage_stocktake_items (
    stocktake_item_source_key TEXT, stocktake_source_key TEXT,
    product_id TEXT, inventory_unit TEXT, physical_quantity TEXT,
    system_quantity TEXT, variance TEXT, review_status TEXT
);
"""


def build_import_sql(
    dataset_dir: str | Path,
    manifest: dict[str, Any],
    reset: bool,
) -> str:
    dataset_path = Path(dataset_dir).resolve()
    reset_sql = """
TRUNCATE TABLE
    inventory_movements,
    stocktake_items,
    stocktakes,
    goods_receipt_items,
    goods_receipts,
    purchase_order_items,
    purchase_orders,
    pos_sales,
    dataset_imports
RESTART IDENTITY;
""" if reset else ""

    copy_specs = (
        ("stage_menu_items", "menu_items.csv"),
        ("stage_recipes", "recipes.csv"),
        ("stage_purchase_orders", "purchase_orders.csv"),
        ("stage_purchase_order_items", "purchase_order_items.csv"),
        ("stage_goods_receipts", "goods_receipts.csv"),
        ("stage_goods_receipt_items", "goods_receipt_items.csv"),
        ("stage_pos_sales", "pos_sales.csv"),
        ("stage_inventory_movements", "inventory_movements.csv"),
        ("stage_stocktakes", "stocktakes.csv"),
        ("stage_stocktake_items", "stocktake_items.csv"),
    )
    copies = "\n".join(
        copy_command(table, dataset_path / filename)
        for table, filename in copy_specs
    )
    row_counts = json.dumps(manifest["row_counts"], sort_keys=True)

    return f"""
\\set ON_ERROR_STOP on
BEGIN;
SET search_path TO cafe_stock_manage, public;
{reset_sql}
{stage_table_sql()}
{copies}

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM stage_stocktake_items AS s
        WHERE s.physical_quantity::NUMERIC - s.system_quantity::NUMERIC
            <> s.variance::NUMERIC
    ) THEN
        RAISE EXCEPTION 'Staged stocktake variance does not match physical minus system';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM stage_stocktake_items AS s
        JOIN products AS p ON p.product_id = s.product_id
        WHERE s.inventory_unit <> p.inventory_unit
    ) THEN
        RAISE EXCEPTION 'Staged stocktake unit does not match Product Master';
    END IF;
END;
$$;

INSERT INTO menu_items (
    menu_item_id, menu_item_name, menu_category, selling_price, notes
)
SELECT
    menu_item_id,
    menu_item_name,
    menu_category,
    selling_price::NUMERIC,
    'Synthetic demo assumption'
FROM stage_menu_items
ON CONFLICT (menu_item_id) DO UPDATE SET
    menu_item_name = EXCLUDED.menu_item_name,
    menu_category = EXCLUDED.menu_category,
    selling_price = EXCLUDED.selling_price;

INSERT INTO recipes (
    menu_item_id, product_id, ingredient_quantity, ingredient_unit, notes
)
SELECT
    menu_item_id,
    product_id,
    ingredient_quantity::NUMERIC,
    ingredient_unit,
    'Synthetic demo assumption'
FROM stage_recipes
ON CONFLICT (menu_item_id, product_id) DO UPDATE SET
    ingredient_quantity = EXCLUDED.ingredient_quantity,
    ingredient_unit = EXCLUDED.ingredient_unit;

INSERT INTO purchase_orders (
    source_key, supplier_id, order_datetime, expected_delivery_date,
    order_status, ordered_by, notes
)
SELECT
    po_source_key,
    supplier_id,
    order_datetime::TIMESTAMPTZ,
    expected_delivery_date::DATE,
    order_status,
    ordered_by,
    'Imported synthetic dataset'
FROM stage_purchase_orders;

INSERT INTO purchase_order_items (
    source_key, po_id, product_id, ordered_quantity, order_unit
)
SELECT
    s.po_item_source_key,
    po.po_id,
    s.product_id,
    s.ordered_quantity::NUMERIC,
    s.order_unit
FROM stage_purchase_order_items AS s
JOIN purchase_orders AS po
  ON po.source_key = s.po_source_key;

INSERT INTO goods_receipts (
    source_key, po_id, supplier_id, received_datetime, invoice_number,
    received_by, receipt_status, notes
)
SELECT
    s.receipt_source_key,
    po.po_id,
    s.supplier_id,
    s.received_datetime::TIMESTAMPTZ,
    s.invoice_number,
    s.received_by,
    s.receipt_status,
    'Imported synthetic dataset'
FROM stage_goods_receipts AS s
JOIN purchase_orders AS po
  ON po.source_key = s.po_source_key;

INSERT INTO goods_receipt_items (
    source_key, receipt_id, po_item_id, product_id, invoice_quantity,
    received_quantity, damaged_quantity, accepted_quantity,
    wrong_item_flag, discrepancy_reason, notes
)
SELECT
    s.receipt_item_source_key,
    gr.receipt_id,
    poi.po_item_id,
    s.product_id,
    s.invoice_quantity::NUMERIC,
    s.received_quantity::NUMERIC,
    s.damaged_quantity::NUMERIC,
    s.accepted_quantity::NUMERIC,
    s.wrong_item_flag::BOOLEAN,
    s.discrepancy_reason,
    'Imported synthetic dataset'
FROM stage_goods_receipt_items AS s
JOIN goods_receipts AS gr
  ON gr.source_key = s.receipt_source_key
JOIN purchase_order_items AS poi
  ON poi.source_key = s.po_item_source_key;

INSERT INTO pos_sales (
    source_key, sale_date, menu_item_id, quantity_sold, unit_price, notes
)
SELECT
    pos_source_key,
    sale_date::DATE,
    menu_item_id,
    quantity_sold::INTEGER,
    unit_price::NUMERIC,
    'Imported synthetic dataset'
FROM stage_pos_sales;

INSERT INTO stocktakes (
    source_key, stocktake_datetime, stocktake_status, performed_by,
    notes, reconciled_at
)
SELECT
    stocktake_source_key,
    stocktake_datetime::TIMESTAMPTZ,
    stocktake_status,
    performed_by,
    'Imported synthetic dataset',
    CASE
        WHEN stocktake_status = 'RECONCILED'
            THEN stocktake_datetime::TIMESTAMPTZ
        ELSE NULL
    END
FROM stage_stocktakes;

INSERT INTO stocktake_items (
    source_key, stocktake_id, product_id, physical_quantity,
    system_quantity, review_status, notes
)
SELECT
    s.stocktake_item_source_key,
    st.stocktake_id,
    s.product_id,
    s.physical_quantity::NUMERIC,
    s.system_quantity::NUMERIC,
    s.review_status,
    'Imported synthetic dataset'
FROM stage_stocktake_items AS s
JOIN stocktakes AS st
  ON st.source_key = s.stocktake_source_key;

INSERT INTO inventory_movements (
    movement_source_key, product_id, movement_datetime, movement_type,
    quantity_change, receipt_item_id, source_type, source_id,
    reason_code, recorded_by, notes
)
SELECT
    s.movement_source_key,
    s.product_id,
    s.movement_datetime::TIMESTAMPTZ,
    s.movement_type,
    s.quantity_change::NUMERIC,
    CASE WHEN s.source_type = 'GOODS_RECEIPT' THEN gri.receipt_item_id END,
    s.source_type,
    s.source_id,
    NULLIF(s.reason_code, ''),
    s.recorded_by,
    'Imported synthetic dataset'
FROM stage_inventory_movements AS s
LEFT JOIN goods_receipt_items AS gri
  ON gri.source_key = s.source_id;

UPDATE pos_sales AS ps
SET
    usage_posted_at = usage.latest_movement_datetime,
    usage_posted_by = 'SYSTEM'
FROM (
    SELECT
        source_id,
        MAX(movement_datetime) AS latest_movement_datetime
    FROM inventory_movements
    WHERE source_type = 'POS_SALE'
    GROUP BY source_id
) AS usage
WHERE ps.source_key = usage.source_id;

INSERT INTO dataset_imports (
    dataset_sha256, scenario, start_date, days, random_seed, row_counts
)
VALUES (
    {sql_literal(manifest['dataset_sha256'])},
    {sql_literal(manifest['scenario'])},
    {sql_literal(manifest['start_date'])}::DATE,
    {int(manifest['days'])},
    {int(manifest['random_seed'])},
    {sql_literal(row_counts)}::JSONB
);

DO $$
DECLARE
    issue_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO issue_count FROM data_quality_issues;
    IF issue_count > 0 THEN
        RAISE EXCEPTION 'Loaded dataset has % data quality issues', issue_count;
    END IF;
END;
$$;

COMMIT;
"""


def load_dataset(
    dataset_dir: str | Path,
    connection: str,
    reset: bool = False,
) -> str:
    manifest = validate_dataset(dataset_dir)
    try:
        imported_hashes, operational_count = inspect_database(connection)
    except DatasetLoadError as error:
        raise DatasetLoadError(
            f"Database is not ready for import; apply migrations and seeds first. {error}"
        ) from error

    dataset_hash = manifest["dataset_sha256"]
    if dataset_hash in imported_hashes:
        return "already_loaded"
    if (imported_hashes or operational_count > 0) and not reset:
        raise DatasetLoadError(
            "The database already contains operational data. Use --reset to replace it."
        )

    run_psql(
        connection,
        build_import_sql(dataset_dir, manifest, reset=reset),
    )
    return "loaded"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_dir", help="Generated dataset directory")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", "cafe_stock_manage_dev"),
        help="PostgreSQL connection string or database name",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Replace existing operational data while preserving master data",
    )
    args = parser.parse_args()

    try:
        status = load_dataset(args.dataset_dir, args.database_url, reset=args.reset)
        manifest = validate_dataset(args.dataset_dir)
    except DatasetLoadError as error:
        parser.exit(1, f"error: {error}\n")
    if status == "already_loaded":
        print(f"Dataset {manifest['dataset_sha256']} is already loaded.")
    else:
        print(
            f"Loaded {manifest['scenario']} dataset {manifest['dataset_sha256']} "
            f"into PostgreSQL."
        )


if __name__ == "__main__":
    main()
