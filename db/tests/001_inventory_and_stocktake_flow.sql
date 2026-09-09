\set ON_ERROR_STOP on

BEGIN;

SET search_path TO cafe_stock_manage, public;

DO $$
DECLARE
    v_po_id BIGINT;
    v_oat_po_item_id BIGINT;
    v_egg_po_item_id BIGINT;
    v_receipt_id BIGINT;
    v_stocktake_id BIGINT;
    v_stocktake_item_id BIGINT;
    v_movement_id BIGINT;
    v_quantity NUMERIC(14, 4);
    v_variance NUMERIC(14, 4);
    v_receive_count INTEGER;
    v_immutability_blocked BOOLEAN := FALSE;
BEGIN
    INSERT INTO suppliers (
        supplier_id,
        supplier_name,
        supplier_type,
        default_lead_time_days
    )
    VALUES ('TEST_SUPPLIER', 'Test Supplier', 'SCHEDULED', 1);

    INSERT INTO products (
        product_id,
        product_name,
        category,
        inventory_unit,
        order_unit,
        pack_size,
        content_quantity_per_inventory_unit,
        content_unit,
        supplier_id
    )
    VALUES
        ('TEST_OAT', 'Test Oat Milk', 'MILK', 'carton', 'carton', 1, 1, 'litre', 'TEST_SUPPLIER'),
        ('TEST_EGGS', 'Test Eggs', 'FOOD', 'each', 'tray', 25, NULL, NULL, 'TEST_SUPPLIER');

    INSERT INTO purchase_orders (
        supplier_id,
        order_datetime,
        expected_delivery_date,
        order_status,
        ordered_by
    )
    VALUES (
        'TEST_SUPPLIER',
        TIMESTAMPTZ '2026-09-01 14:00:00+10',
        DATE '2026-09-02',
        'SUBMITTED',
        'Manager'
    )
    RETURNING po_id INTO v_po_id;

    INSERT INTO purchase_order_items (
        po_id,
        product_id,
        ordered_quantity,
        order_unit,
        unit_cost
    )
    VALUES (v_po_id, 'TEST_OAT', 8, 'carton', 3.50)
    RETURNING po_item_id INTO v_oat_po_item_id;

    INSERT INTO purchase_order_items (
        po_id,
        product_id,
        ordered_quantity,
        order_unit,
        unit_cost
    )
    VALUES (v_po_id, 'TEST_EGGS', 9, 'tray', 12.00)
    RETURNING po_item_id INTO v_egg_po_item_id;

    INSERT INTO goods_receipts (
        po_id,
        supplier_id,
        received_datetime,
        invoice_number,
        received_by,
        receipt_status
    )
    VALUES (
        v_po_id,
        'TEST_SUPPLIER',
        TIMESTAMPTZ '2026-09-02 08:00:00+10',
        'TEST-INV-001',
        'Manager',
        'CHECKED'
    )
    RETURNING receipt_id INTO v_receipt_id;

    INSERT INTO goods_receipt_items (
        receipt_id,
        po_item_id,
        product_id,
        invoice_quantity,
        received_quantity,
        damaged_quantity,
        accepted_quantity,
        discrepancy_reason
    )
    VALUES
        (v_receipt_id, v_oat_po_item_id, 'TEST_OAT', 8, 6, 0, 6, 'SHORT_DELIVERY'),
        (v_receipt_id, v_egg_po_item_id, 'TEST_EGGS', 9, 9, 0, 9, 'NONE');

    PERFORM movement_id
    FROM post_goods_receipt(v_receipt_id, 'Manager');

    SELECT current_quantity
    INTO v_quantity
    FROM inventory_balance
    WHERE product_id = 'TEST_OAT';

    IF v_quantity <> 6 THEN
        RAISE EXCEPTION 'Expected 6 oat cartons after receipt, got %', v_quantity;
    END IF;

    SELECT current_quantity
    INTO v_quantity
    FROM inventory_balance
    WHERE product_id = 'TEST_EGGS';

    IF v_quantity <> 225 THEN
        RAISE EXCEPTION 'Expected 225 eggs after receiving 9 trays, got %', v_quantity;
    END IF;

    INSERT INTO inventory_movements (
        product_id,
        movement_datetime,
        movement_type,
        quantity_change,
        source_type,
        source_id,
        recorded_by
    )
    VALUES (
        'TEST_OAT',
        TIMESTAMPTZ '2026-09-02 16:00:00+10',
        'USE',
        -2.4,
        'MANUAL_USAGE',
        'TEST-USAGE-001',
        'Manager'
    )
    RETURNING movement_id INTO v_movement_id;

    SELECT current_quantity
    INTO v_quantity
    FROM inventory_balance
    WHERE product_id = 'TEST_OAT';

    IF v_quantity <> 3.6 THEN
        RAISE EXCEPTION 'Expected 3.6 oat cartons after use, got %', v_quantity;
    END IF;

    INSERT INTO stocktakes (
        stocktake_datetime,
        performed_by,
        notes
    )
    VALUES (
        TIMESTAMPTZ '2026-09-02 18:00:00+10',
        'Manager',
        'Daily closing count'
    )
    RETURNING stocktake_id INTO v_stocktake_id;

    v_stocktake_item_id := record_stocktake_count(
        v_stocktake_id,
        'TEST_OAT',
        3
    );

    SELECT variance
    INTO v_variance
    FROM stocktake_items
    WHERE stocktake_item_id = v_stocktake_item_id;

    IF v_variance <> -0.6 THEN
        RAISE EXCEPTION 'Expected stocktake variance -0.6, got %', v_variance;
    END IF;

    PERFORM movement_id
    FROM reconcile_stocktake(v_stocktake_id, 'Manager');

    SELECT current_quantity
    INTO v_quantity
    FROM inventory_balance
    WHERE product_id = 'TEST_OAT';

    IF v_quantity <> 3 THEN
        RAISE EXCEPTION 'Expected 3 oat cartons after reconciliation, got %', v_quantity;
    END IF;

    PERFORM movement_id
    FROM post_goods_receipt(v_receipt_id, 'Manager');

    SELECT COUNT(*)
    INTO v_receive_count
    FROM inventory_movements
    WHERE source_type = 'GOODS_RECEIPT'
      AND product_id IN ('TEST_OAT', 'TEST_EGGS');

    IF v_receive_count <> 2 THEN
        RAISE EXCEPTION 'Receipt posting was not idempotent; found % movements', v_receive_count;
    END IF;

    BEGIN
        UPDATE inventory_movements
        SET notes = 'This update must be blocked'
        WHERE movement_id = v_movement_id;
    EXCEPTION
        WHEN raise_exception THEN
            v_immutability_blocked := TRUE;
    END;

    IF NOT v_immutability_blocked THEN
        RAISE EXCEPTION 'Inventory movement update was not blocked';
    END IF;
END;
$$;

ROLLBACK;
