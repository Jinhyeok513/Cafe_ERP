BEGIN;

SET search_path TO cafe_stock_manage, public;

DO $$
DECLARE
    v_recommendation_count INTEGER;
    v_egg_order_unit TEXT;
    v_egg_pack_size NUMERIC;
BEGIN
    SELECT COUNT(*)
    INTO v_recommendation_count
    FROM reorder_recommendations
    WHERE recommended_order_quantity > 0;

    IF v_recommendation_count = 0 THEN
        RAISE EXCEPTION 'Expected at least one reorder recommendation';
    END IF;

    SELECT order_unit, pack_size
    INTO v_egg_order_unit, v_egg_pack_size
    FROM reorder_recommendations
    WHERE product_id = 'EGGS';

    IF v_egg_order_unit <> 'tray' OR v_egg_pack_size <> 25 THEN
        RAISE EXCEPTION 'Egg recommendation must be expressed as 25-each trays';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM reorder_recommendations
        WHERE expected_delivery_date < CURRENT_DATE
           OR recommended_order_quantity < 0
    ) THEN
        RAISE EXCEPTION 'Reorder dates and quantities must be nonnegative';
    END IF;
END;
$$;

ROLLBACK;
