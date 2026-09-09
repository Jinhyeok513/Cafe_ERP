BEGIN;

SET search_path TO cafe_stock_manage, public;

CREATE TABLE stocktakes (
    stocktake_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    stocktake_datetime TIMESTAMPTZ NOT NULL,
    stocktake_status TEXT NOT NULL DEFAULT 'DRAFT',
    performed_by TEXT NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reconciled_at TIMESTAMPTZ,
    CONSTRAINT stocktakes_status_valid
        CHECK (stocktake_status IN ('DRAFT', 'COUNTED', 'RECONCILED', 'CANCELLED'))
);

CREATE TABLE stocktake_items (
    stocktake_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    stocktake_id BIGINT NOT NULL REFERENCES stocktakes (stocktake_id),
    product_id TEXT NOT NULL REFERENCES products (product_id),
    physical_quantity NUMERIC(14, 4) NOT NULL,
    system_quantity NUMERIC(14, 4) NOT NULL,
    variance NUMERIC(14, 4)
        GENERATED ALWAYS AS (physical_quantity - system_quantity) STORED,
    review_status TEXT NOT NULL,
    notes TEXT,
    CONSTRAINT stocktake_items_physical_nonnegative CHECK (physical_quantity >= 0),
    CONSTRAINT stocktake_items_status_valid
        CHECK (review_status IN ('MATCH', 'VARIANCE', 'ADJUSTED')),
    CONSTRAINT stocktake_items_one_count_per_product
        UNIQUE (stocktake_id, product_id)
);

COMMENT ON COLUMN stocktake_items.physical_quantity IS
    'Physical count expressed in products.inventory_unit.';
COMMENT ON COLUMN stocktake_items.system_quantity IS
    'Inventory ledger balance captured when the count is recorded.';

CREATE FUNCTION record_stocktake_count(
    p_stocktake_id BIGINT,
    p_product_id TEXT,
    p_physical_quantity NUMERIC
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_system_quantity NUMERIC(14, 4);
    v_stocktake_item_id BIGINT;
BEGIN
    IF p_physical_quantity < 0 THEN
        RAISE EXCEPTION 'Physical quantity cannot be negative';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM stocktakes AS s
        WHERE s.stocktake_id = p_stocktake_id
          AND s.stocktake_status IN ('DRAFT', 'COUNTED')
    ) THEN
        RAISE EXCEPTION 'Stocktake % must be DRAFT or COUNTED', p_stocktake_id;
    END IF;

    SELECT ib.current_quantity
    INTO v_system_quantity
    FROM inventory_balance AS ib
    WHERE ib.product_id = p_product_id;

    IF v_system_quantity IS NULL THEN
        RAISE EXCEPTION 'Unknown product %', p_product_id;
    END IF;

    INSERT INTO stocktake_items (
        stocktake_id,
        product_id,
        physical_quantity,
        system_quantity,
        review_status
    )
    VALUES (
        p_stocktake_id,
        p_product_id,
        p_physical_quantity,
        v_system_quantity,
        CASE
            WHEN p_physical_quantity = v_system_quantity THEN 'MATCH'
            ELSE 'VARIANCE'
        END
    )
    ON CONFLICT (stocktake_id, product_id)
    DO UPDATE SET
        physical_quantity = EXCLUDED.physical_quantity,
        system_quantity = EXCLUDED.system_quantity,
        review_status = EXCLUDED.review_status
    RETURNING stocktake_item_id
    INTO v_stocktake_item_id;

    UPDATE stocktakes
    SET stocktake_status = 'COUNTED'
    WHERE stocktake_id = p_stocktake_id;

    RETURN v_stocktake_item_id;
END;
$$;

CREATE FUNCTION reconcile_stocktake(
    p_stocktake_id BIGINT,
    p_recorded_by TEXT
)
RETURNS TABLE (movement_id BIGINT)
LANGUAGE plpgsql
AS $$
BEGIN
    IF NULLIF(BTRIM(p_recorded_by), '') IS NULL THEN
        RAISE EXCEPTION 'recorded_by is required';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM stocktakes AS s
        WHERE s.stocktake_id = p_stocktake_id
          AND s.stocktake_status IN ('COUNTED', 'RECONCILED')
    ) THEN
        RAISE EXCEPTION 'Stocktake % must be COUNTED before reconciliation', p_stocktake_id;
    END IF;

    RETURN QUERY
    INSERT INTO inventory_movements (
        product_id,
        movement_datetime,
        movement_type,
        quantity_change,
        source_type,
        source_id,
        reason_code,
        recorded_by,
        notes
    )
    SELECT
        si.product_id,
        s.stocktake_datetime,
        'ADJUSTMENT',
        si.variance,
        'STOCKTAKE',
        si.stocktake_item_id::TEXT,
        'STOCKTAKE_CORRECTION',
        p_recorded_by,
        si.notes
    FROM stocktakes AS s
    JOIN stocktake_items AS si
      ON si.stocktake_id = s.stocktake_id
    WHERE s.stocktake_id = p_stocktake_id
      AND si.variance <> 0
    ON CONFLICT (source_type, source_id, product_id, movement_type) DO NOTHING
    RETURNING inventory_movements.movement_id;

    UPDATE stocktake_items
    SET review_status = CASE
        WHEN variance = 0 THEN 'MATCH'
        ELSE 'ADJUSTED'
    END
    WHERE stocktake_id = p_stocktake_id;

    UPDATE stocktakes
    SET
        stocktake_status = 'RECONCILED',
        reconciled_at = CURRENT_TIMESTAMP
    WHERE stocktake_id = p_stocktake_id;
END;
$$;

CREATE VIEW stocktake_summary AS
SELECT
    s.stocktake_id,
    s.stocktake_datetime,
    s.stocktake_status,
    s.performed_by,
    COUNT(si.stocktake_item_id) AS products_counted,
    COUNT(*) FILTER (WHERE si.variance <> 0) AS products_with_variance,
    COALESCE(SUM(ABS(si.variance)), 0)::NUMERIC(14, 4) AS absolute_variance_quantity
FROM stocktakes AS s
LEFT JOIN stocktake_items AS si
  ON si.stocktake_id = s.stocktake_id
GROUP BY
    s.stocktake_id,
    s.stocktake_datetime,
    s.stocktake_status,
    s.performed_by;

COMMIT;
