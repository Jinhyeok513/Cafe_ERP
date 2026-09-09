BEGIN;

SET search_path TO cafe_stock_manage, public;

CREATE TABLE dataset_imports (
    import_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_sha256 TEXT NOT NULL UNIQUE,
    scenario TEXT NOT NULL,
    start_date DATE NOT NULL,
    days INTEGER NOT NULL,
    random_seed INTEGER NOT NULL,
    row_counts JSONB NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT dataset_imports_scenario_valid CHECK (scenario IN ('clean', 'errors')),
    CONSTRAINT dataset_imports_days_positive CHECK (days > 0),
    CONSTRAINT dataset_imports_sha256_format
        CHECK (dataset_sha256 ~ '^[0-9a-f]{64}$')
);

ALTER TABLE purchase_orders ADD COLUMN source_key TEXT;
ALTER TABLE purchase_order_items ADD COLUMN source_key TEXT;
ALTER TABLE goods_receipts ADD COLUMN source_key TEXT;
ALTER TABLE goods_receipt_items ADD COLUMN source_key TEXT;
ALTER TABLE stocktakes ADD COLUMN source_key TEXT;
ALTER TABLE stocktake_items ADD COLUMN source_key TEXT;
ALTER TABLE pos_sales ADD COLUMN source_key TEXT;
ALTER TABLE inventory_movements ADD COLUMN movement_source_key TEXT;

CREATE UNIQUE INDEX purchase_orders_source_key_unique
    ON purchase_orders (source_key) WHERE source_key IS NOT NULL;
CREATE UNIQUE INDEX purchase_order_items_source_key_unique
    ON purchase_order_items (source_key) WHERE source_key IS NOT NULL;
CREATE UNIQUE INDEX goods_receipts_source_key_unique
    ON goods_receipts (source_key) WHERE source_key IS NOT NULL;
CREATE UNIQUE INDEX goods_receipt_items_source_key_unique
    ON goods_receipt_items (source_key) WHERE source_key IS NOT NULL;
CREATE UNIQUE INDEX stocktakes_source_key_unique
    ON stocktakes (source_key) WHERE source_key IS NOT NULL;
CREATE UNIQUE INDEX stocktake_items_source_key_unique
    ON stocktake_items (source_key) WHERE source_key IS NOT NULL;
CREATE UNIQUE INDEX pos_sales_source_key_unique
    ON pos_sales (source_key) WHERE source_key IS NOT NULL;
CREATE UNIQUE INDEX inventory_movements_source_key_unique
    ON inventory_movements (movement_source_key)
    WHERE movement_source_key IS NOT NULL;

COMMENT ON TABLE dataset_imports IS
    'One row per synthetic dataset loaded into the operational schema.';
COMMENT ON COLUMN purchase_orders.source_key IS
    'Stable external key used for deterministic dataset import and future integrations.';
COMMENT ON COLUMN inventory_movements.movement_source_key IS
    'Stable external key for an imported immutable movement.';

CREATE VIEW inventory_movement_timeline AS
SELECT
    im.movement_id,
    im.movement_source_key,
    im.product_id,
    p.product_name,
    p.category,
    p.inventory_unit,
    im.movement_datetime,
    im.movement_type,
    im.quantity_change,
    SUM(im.quantity_change) OVER (
        PARTITION BY im.product_id
        ORDER BY im.movement_datetime, im.movement_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )::NUMERIC(14, 4) AS running_quantity,
    im.source_type,
    im.source_id,
    im.reason_code,
    im.recorded_by
FROM inventory_movements AS im
JOIN products AS p
  ON p.product_id = im.product_id;

CREATE VIEW current_inventory_status AS
SELECT
    ib.product_id,
    ib.product_name,
    ib.category,
    ib.inventory_unit,
    ib.current_quantity,
    p.reorder_point_inventory_qty,
    CASE
        WHEN ib.current_quantity < 0 THEN 'NEGATIVE_STOCK'
        WHEN p.reorder_point_inventory_qty IS NULL THEN 'NO_REORDER_POINT'
        WHEN ib.current_quantity <= p.reorder_point_inventory_qty THEN 'REORDER_DUE'
        ELSE 'IN_STOCK'
    END AS stock_status
FROM inventory_balance AS ib
JOIN products AS p
  ON p.product_id = ib.product_id;

CREATE VIEW receiving_discrepancy_summary AS
SELECT
    gr.supplier_id,
    gri.discrepancy_reason,
    COUNT(*) AS receipt_lines,
    SUM(gri.invoice_quantity)::NUMERIC(14, 4) AS invoice_quantity,
    SUM(gri.received_quantity)::NUMERIC(14, 4) AS received_quantity,
    SUM(gri.accepted_quantity)::NUMERIC(14, 4) AS accepted_quantity
FROM goods_receipt_items AS gri
JOIN goods_receipts AS gr
  ON gr.receipt_id = gri.receipt_id
WHERE gri.discrepancy_reason <> 'NONE'
GROUP BY gr.supplier_id, gri.discrepancy_reason;

CREATE VIEW stocktake_accuracy_daily AS
SELECT
    s.stocktake_id,
    s.source_key,
    s.stocktake_datetime::DATE AS stocktake_date,
    COUNT(*) AS products_counted,
    COUNT(*) FILTER (WHERE si.variance = 0) AS products_matched,
    COUNT(*) FILTER (WHERE si.variance <> 0) AS products_with_variance,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE si.variance = 0) / NULLIF(COUNT(*), 0),
        2
    ) AS inventory_accuracy_percent,
    SUM(ABS(si.variance))::NUMERIC(14, 4) AS absolute_variance_quantity
FROM stocktakes AS s
JOIN stocktake_items AS si
  ON si.stocktake_id = s.stocktake_id
GROUP BY s.stocktake_id, s.source_key, s.stocktake_datetime;

CREATE VIEW data_quality_issues AS
WITH receipt_movement AS (
    SELECT
        gri.receipt_item_id,
        SUM(im.quantity_change)::NUMERIC(14, 4) AS actual_quantity
    FROM goods_receipt_items AS gri
    JOIN inventory_movements AS im
      ON im.receipt_item_id = gri.receipt_item_id
     AND im.movement_type = 'RECEIVE'
    GROUP BY gri.receipt_item_id
),
stocktake_adjustment AS (
    SELECT
        si.stocktake_item_id,
        SUM(im.quantity_change)::NUMERIC(14, 4) AS actual_quantity
    FROM stocktake_items AS si
    JOIN inventory_movements AS im
      ON im.source_type = 'STOCKTAKE'
     AND (
        im.source_id = si.stocktake_item_id::TEXT
        OR im.source_id = si.source_key
     )
    GROUP BY si.stocktake_item_id
),
expected_pos_usage AS (
    SELECT
        ps.pos_sale_id,
        ps.source_key,
        rir.product_id,
        (-ps.quantity_sold * rir.inventory_quantity_per_menu_item)::NUMERIC(14, 4)
            AS expected_quantity
    FROM pos_sales AS ps
    JOIN recipe_inventory_requirements AS rir
      ON rir.menu_item_id = ps.menu_item_id
),
actual_pos_usage AS (
    SELECT
        ps.pos_sale_id,
        im.product_id,
        SUM(im.quantity_change)::NUMERIC(14, 4) AS actual_quantity
    FROM pos_sales AS ps
    JOIN inventory_movements AS im
      ON im.source_type = 'POS_SALE'
     AND (
        im.source_id = ps.pos_sale_id::TEXT
        OR im.source_id = ps.source_key
     )
    GROUP BY ps.pos_sale_id, im.product_id
)
SELECT
    'NEGATIVE_CURRENT_STOCK'::TEXT AS issue_code,
    'ERROR'::TEXT AS severity,
    'product'::TEXT AS entity_type,
    cis.product_id::TEXT AS entity_id,
    ('Current quantity is ' || cis.current_quantity || ' ' || cis.inventory_unit)::TEXT
        AS details
FROM current_inventory_status AS cis
WHERE cis.current_quantity < 0

UNION ALL

SELECT
    'RECEIPT_MOVEMENT_MISMATCH',
    'ERROR',
    'goods_receipt_item',
    COALESCE(gri.source_key, gri.receipt_item_id::TEXT),
    (
        'Expected ' || (gri.accepted_quantity * p.pack_size) ||
        ', recorded ' || COALESCE(rm.actual_quantity, 0) ||
        ' ' || p.inventory_unit
    )
FROM goods_receipt_items AS gri
JOIN products AS p
  ON p.product_id = gri.product_id
LEFT JOIN receipt_movement AS rm
  ON rm.receipt_item_id = gri.receipt_item_id
WHERE gri.accepted_quantity * p.pack_size <> COALESCE(rm.actual_quantity, 0)

UNION ALL

SELECT
    'STOCKTAKE_ADJUSTMENT_MISMATCH',
    'ERROR',
    'stocktake_item',
    COALESCE(si.source_key, si.stocktake_item_id::TEXT),
    (
        'Expected adjustment ' || si.variance ||
        ', recorded ' || COALESCE(sa.actual_quantity, 0)
    )
FROM stocktake_items AS si
LEFT JOIN stocktake_adjustment AS sa
  ON sa.stocktake_item_id = si.stocktake_item_id
WHERE si.variance <> COALESCE(sa.actual_quantity, 0)

UNION ALL

SELECT
    'POS_USAGE_MOVEMENT_MISMATCH',
    'ERROR',
    'pos_sale',
    COALESCE(epu.source_key, epu.pos_sale_id::TEXT),
    (
        'Product ' || epu.product_id || ': expected ' || epu.expected_quantity ||
        ', recorded ' || COALESCE(apu.actual_quantity, 0)
    )
FROM expected_pos_usage AS epu
LEFT JOIN actual_pos_usage AS apu
  ON apu.pos_sale_id = epu.pos_sale_id
 AND apu.product_id = epu.product_id
WHERE epu.expected_quantity <> COALESCE(apu.actual_quantity, 0);

COMMIT;
