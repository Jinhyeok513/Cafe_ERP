BEGIN;

SET search_path TO cafe_stock_manage, public;

CREATE TABLE inventory_movements (
    movement_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id TEXT NOT NULL REFERENCES products (product_id),
    movement_datetime TIMESTAMPTZ NOT NULL,
    movement_type TEXT NOT NULL,
    quantity_change NUMERIC(14, 4) NOT NULL,
    receipt_item_id BIGINT REFERENCES goods_receipt_items (receipt_item_id),
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    reason_code TEXT,
    recorded_by TEXT NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT inventory_movements_type_valid
        CHECK (movement_type IN ('RECEIVE', 'USE', 'WASTE', 'ADJUSTMENT')),
    CONSTRAINT inventory_movements_source_type_valid
        CHECK (
            source_type IN (
                'GOODS_RECEIPT',
                'POS_SALE',
                'STOCKTAKE',
                'WASTE_LOG',
                'MANUAL_USAGE',
                'MANUAL_ADJUSTMENT',
                'OPENING_BALANCE'
            )
        ),
    CONSTRAINT inventory_movements_quantity_sign_valid
        CHECK (
            (movement_type = 'RECEIVE' AND quantity_change > 0)
            OR (movement_type IN ('USE', 'WASTE') AND quantity_change < 0)
            OR (movement_type = 'ADJUSTMENT' AND quantity_change <> 0)
        ),
    CONSTRAINT inventory_movements_receipt_source_consistent
        CHECK (
            (movement_type = 'RECEIVE'
                AND source_type = 'GOODS_RECEIPT'
                AND receipt_item_id IS NOT NULL)
            OR (movement_type <> 'RECEIVE' AND receipt_item_id IS NULL)
        ),
    CONSTRAINT inventory_movements_reason_present
        CHECK (
            movement_type NOT IN ('WASTE', 'ADJUSTMENT')
            OR NULLIF(BTRIM(reason_code), '') IS NOT NULL
        ),
    CONSTRAINT inventory_movements_source_unique
        UNIQUE (source_type, source_id, product_id, movement_type)
);

CREATE UNIQUE INDEX inventory_movements_one_receive_per_receipt_item
    ON inventory_movements (receipt_item_id)
    WHERE receipt_item_id IS NOT NULL;

COMMENT ON COLUMN inventory_movements.quantity_change IS
    'Signed quantity expressed in the product inventory_unit. RECEIVE is positive; USE and WASTE are negative.';
COMMENT ON COLUMN inventory_movements.source_id IS
    'Identifier of the originating receipt item, POS row, stocktake item or manual event.';

CREATE VIEW inventory_balance AS
SELECT
    p.product_id,
    p.product_name,
    p.category,
    p.inventory_unit,
    COALESCE(SUM(im.quantity_change), 0)::NUMERIC(14, 4) AS current_quantity
FROM products AS p
LEFT JOIN inventory_movements AS im
    ON im.product_id = p.product_id
GROUP BY
    p.product_id,
    p.product_name,
    p.category,
    p.inventory_unit;

CREATE FUNCTION post_goods_receipt(
    p_receipt_id BIGINT,
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
        FROM goods_receipts AS gr
        WHERE gr.receipt_id = p_receipt_id
          AND gr.receipt_status IN ('CHECKED', 'POSTED')
    ) THEN
        RAISE EXCEPTION 'Receipt % must exist and be CHECKED before posting', p_receipt_id;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM goods_receipt_items AS gri
        JOIN purchase_order_items AS poi
          ON poi.po_item_id = gri.po_item_id
        JOIN products AS p
          ON p.product_id = gri.product_id
        WHERE gri.receipt_id = p_receipt_id
          AND poi.order_unit <> p.order_unit
    ) THEN
        RAISE EXCEPTION 'Receipt % contains an order unit that does not match Product Master', p_receipt_id;
    END IF;

    RETURN QUERY
    INSERT INTO inventory_movements (
        product_id,
        movement_datetime,
        movement_type,
        quantity_change,
        receipt_item_id,
        source_type,
        source_id,
        reason_code,
        recorded_by,
        notes
    )
    SELECT
        gri.product_id,
        gr.received_datetime,
        'RECEIVE',
        gri.accepted_quantity * p.pack_size,
        gri.receipt_item_id,
        'GOODS_RECEIPT',
        gri.receipt_item_id::TEXT,
        NULLIF(gri.discrepancy_reason, 'NONE'),
        p_recorded_by,
        gri.notes
    FROM goods_receipts AS gr
    JOIN goods_receipt_items AS gri
      ON gri.receipt_id = gr.receipt_id
    JOIN products AS p
      ON p.product_id = gri.product_id
    WHERE gr.receipt_id = p_receipt_id
      AND gri.accepted_quantity > 0
    ON CONFLICT (source_type, source_id, product_id, movement_type) DO NOTHING
    RETURNING inventory_movements.movement_id;

    UPDATE goods_receipts
    SET receipt_status = 'POSTED'
    WHERE receipt_id = p_receipt_id;
END;
$$;

CREATE FUNCTION prevent_inventory_movement_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'Inventory movements are immutable; create an ADJUSTMENT movement instead';
END;
$$;

CREATE TRIGGER inventory_movements_no_update_or_delete
BEFORE UPDATE OR DELETE ON inventory_movements
FOR EACH ROW
EXECUTE FUNCTION prevent_inventory_movement_mutation();

COMMIT;
