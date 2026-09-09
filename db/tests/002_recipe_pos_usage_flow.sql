\set ON_ERROR_STOP on

BEGIN;

SET search_path TO cafe_stock_manage, public;

DO $$
DECLARE
    v_pos_sale_id BIGINT;
    v_quantity NUMERIC(14, 4);
    v_required_quantity NUMERIC(14, 6);
    v_use_count INTEGER;
    v_bad_unit_blocked BOOLEAN := FALSE;
    v_posted_sale_change_blocked BOOLEAN := FALSE;
BEGIN
    INSERT INTO suppliers (
        supplier_id,
        supplier_name,
        supplier_type,
        default_lead_time_days
    )
    VALUES ('TEST_POS_SUPPLIER', 'Test POS Supplier', 'SCHEDULED', 1);

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
    VALUES (
        'TEST_POS_OAT',
        'Test POS Oat Milk',
        'MILK',
        'carton',
        'carton',
        1,
        1,
        'litre',
        'TEST_POS_SUPPLIER'
    );

    INSERT INTO menu_items (
        menu_item_id,
        menu_item_name,
        menu_category,
        selling_price
    )
    VALUES ('TEST_OAT_LATTE', 'Test Oat Latte', 'BEVERAGE', 6.50);

    INSERT INTO recipes (
        menu_item_id,
        product_id,
        ingredient_quantity,
        ingredient_unit
    )
    VALUES ('TEST_OAT_LATTE', 'TEST_POS_OAT', 0.25, 'litre');

    BEGIN
        INSERT INTO recipes (
            menu_item_id,
            product_id,
            ingredient_quantity,
            ingredient_unit
        )
        VALUES ('TEST_OAT_LATTE', 'TEST_POS_OAT', 250, 'millilitre');
    EXCEPTION
        WHEN raise_exception THEN
            v_bad_unit_blocked := TRUE;
    END;

    IF NOT v_bad_unit_blocked THEN
        RAISE EXCEPTION 'Recipe unit mismatch was not blocked';
    END IF;

    INSERT INTO inventory_movements (
        product_id,
        movement_datetime,
        movement_type,
        quantity_change,
        source_type,
        source_id,
        reason_code,
        recorded_by
    )
    VALUES (
        'TEST_POS_OAT',
        TIMESTAMPTZ '2026-09-03 06:00:00+10',
        'ADJUSTMENT',
        8,
        'OPENING_BALANCE',
        'TEST-POS-OPENING-001',
        'OPENING_BALANCE',
        'Manager'
    );

    INSERT INTO pos_sales (
        sale_date,
        menu_item_id,
        quantity_sold,
        unit_price
    )
    VALUES (DATE '2026-09-03', 'TEST_OAT_LATTE', 4, 6.50)
    RETURNING pos_sale_id INTO v_pos_sale_id;

    SELECT required_inventory_quantity
    INTO v_required_quantity
    FROM pos_inventory_usage_preview
    WHERE pos_sale_id = v_pos_sale_id
      AND product_id = 'TEST_POS_OAT';

    IF v_required_quantity <> 1 THEN
        RAISE EXCEPTION 'Expected 1 oat carton for 4 test lattes, got %', v_required_quantity;
    END IF;

    PERFORM movement_id
    FROM post_pos_sale_usage(v_pos_sale_id, 'Manager');

    SELECT current_quantity
    INTO v_quantity
    FROM inventory_balance
    WHERE product_id = 'TEST_POS_OAT';

    IF v_quantity <> 7 THEN
        RAISE EXCEPTION 'Expected 7 oat cartons after POS usage, got %', v_quantity;
    END IF;

    PERFORM movement_id
    FROM post_pos_sale_usage(v_pos_sale_id, 'Manager');

    SELECT COUNT(*)
    INTO v_use_count
    FROM inventory_movements
    WHERE source_type = 'POS_SALE'
      AND source_id = v_pos_sale_id::TEXT
      AND product_id = 'TEST_POS_OAT';

    IF v_use_count <> 1 THEN
        RAISE EXCEPTION 'POS posting was not idempotent; found % movements', v_use_count;
    END IF;

    BEGIN
        UPDATE pos_sales
        SET quantity_sold = 5
        WHERE pos_sale_id = v_pos_sale_id;
    EXCEPTION
        WHEN raise_exception THEN
            v_posted_sale_change_blocked := TRUE;
    END;

    IF NOT v_posted_sale_change_blocked THEN
        RAISE EXCEPTION 'Posted POS sale quantity change was not blocked';
    END IF;
END;
$$;

ROLLBACK;
