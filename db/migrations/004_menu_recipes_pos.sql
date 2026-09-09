BEGIN;

SET search_path TO cafe_stock_manage, public;

CREATE TABLE menu_items (
    menu_item_id TEXT PRIMARY KEY,
    menu_item_name TEXT NOT NULL UNIQUE,
    menu_category TEXT NOT NULL,
    selling_price NUMERIC(12, 2) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    CONSTRAINT menu_items_selling_price_nonnegative CHECK (selling_price >= 0)
);

CREATE TABLE recipes (
    recipe_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    menu_item_id TEXT NOT NULL REFERENCES menu_items (menu_item_id),
    product_id TEXT NOT NULL REFERENCES products (product_id),
    ingredient_quantity NUMERIC(14, 6) NOT NULL,
    ingredient_unit TEXT NOT NULL,
    notes TEXT,
    CONSTRAINT recipes_ingredient_quantity_positive CHECK (ingredient_quantity > 0),
    CONSTRAINT recipes_one_ingredient_per_menu_item
        UNIQUE (menu_item_id, product_id)
);

COMMENT ON COLUMN recipes.ingredient_quantity IS
    'Quantity required for one menu item, expressed in ingredient_unit.';
COMMENT ON COLUMN recipes.ingredient_unit IS
    'Must equal the product content_unit when physical content is defined; otherwise must equal inventory_unit.';

CREATE FUNCTION validate_recipe_ingredient_unit()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_expected_unit TEXT;
BEGIN
    SELECT COALESCE(p.content_unit, p.inventory_unit)
    INTO v_expected_unit
    FROM products AS p
    WHERE p.product_id = NEW.product_id;

    IF v_expected_unit IS NULL THEN
        RAISE EXCEPTION 'Unknown recipe product %', NEW.product_id;
    END IF;

    IF NEW.ingredient_unit <> v_expected_unit THEN
        RAISE EXCEPTION
            'Recipe unit % does not match expected unit % for product %',
            NEW.ingredient_unit,
            v_expected_unit,
            NEW.product_id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER recipes_validate_ingredient_unit
BEFORE INSERT OR UPDATE OF product_id, ingredient_unit ON recipes
FOR EACH ROW
EXECUTE FUNCTION validate_recipe_ingredient_unit();

CREATE VIEW recipe_inventory_requirements AS
SELECT
    r.recipe_id,
    r.menu_item_id,
    mi.menu_item_name,
    r.product_id,
    p.product_name,
    r.ingredient_quantity,
    r.ingredient_unit,
    p.inventory_unit,
    CASE
        WHEN p.content_quantity_per_inventory_unit IS NOT NULL
            THEN r.ingredient_quantity / p.content_quantity_per_inventory_unit
        ELSE r.ingredient_quantity
    END::NUMERIC(14, 6) AS inventory_quantity_per_menu_item
FROM recipes AS r
JOIN menu_items AS mi
  ON mi.menu_item_id = r.menu_item_id
JOIN products AS p
  ON p.product_id = r.product_id;

CREATE TABLE pos_sales (
    pos_sale_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sale_date DATE NOT NULL,
    menu_item_id TEXT NOT NULL REFERENCES menu_items (menu_item_id),
    quantity_sold INTEGER NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    gross_revenue NUMERIC(14, 2)
        GENERATED ALWAYS AS (quantity_sold * unit_price) STORED,
    usage_posted_at TIMESTAMPTZ,
    usage_posted_by TEXT,
    notes TEXT,
    CONSTRAINT pos_sales_quantity_positive CHECK (quantity_sold > 0),
    CONSTRAINT pos_sales_unit_price_nonnegative CHECK (unit_price >= 0),
    CONSTRAINT pos_sales_posting_pair_complete
        CHECK (
            (usage_posted_at IS NULL AND usage_posted_by IS NULL)
            OR (usage_posted_at IS NOT NULL AND usage_posted_by IS NOT NULL)
        ),
    CONSTRAINT pos_sales_one_daily_menu_total UNIQUE (sale_date, menu_item_id)
);

COMMENT ON TABLE pos_sales IS
    'Initial grain: one row per sale date and menu item.';

CREATE VIEW pos_inventory_usage_preview AS
SELECT
    ps.pos_sale_id,
    ps.sale_date,
    ps.menu_item_id,
    rir.product_id,
    rir.product_name,
    rir.inventory_unit,
    ps.quantity_sold,
    rir.inventory_quantity_per_menu_item,
    (
        ps.quantity_sold * rir.inventory_quantity_per_menu_item
    )::NUMERIC(14, 6) AS required_inventory_quantity
FROM pos_sales AS ps
JOIN recipe_inventory_requirements AS rir
  ON rir.menu_item_id = ps.menu_item_id;

CREATE FUNCTION post_pos_sale_usage(
    p_pos_sale_id BIGINT,
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
        FROM pos_sales AS ps
        WHERE ps.pos_sale_id = p_pos_sale_id
    ) THEN
        RAISE EXCEPTION 'Unknown POS sale %', p_pos_sale_id;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pos_sales AS ps
        JOIN recipes AS r
          ON r.menu_item_id = ps.menu_item_id
        WHERE ps.pos_sale_id = p_pos_sale_id
    ) THEN
        RAISE EXCEPTION 'POS sale % has no recipe ingredients', p_pos_sale_id;
    END IF;

    RETURN QUERY
    INSERT INTO inventory_movements (
        product_id,
        movement_datetime,
        movement_type,
        quantity_change,
        source_type,
        source_id,
        recorded_by,
        notes
    )
    SELECT
        preview.product_id,
        (preview.sale_date + TIME '23:59:59') AT TIME ZONE 'Australia/Sydney',
        'USE',
        -preview.required_inventory_quantity,
        'POS_SALE',
        preview.pos_sale_id::TEXT,
        p_recorded_by,
        'Recipe-derived usage for ' || preview.menu_item_id
    FROM pos_inventory_usage_preview AS preview
    WHERE preview.pos_sale_id = p_pos_sale_id
      AND preview.required_inventory_quantity > 0
    ON CONFLICT (source_type, source_id, product_id, movement_type) DO NOTHING
    RETURNING inventory_movements.movement_id;

    UPDATE pos_sales
    SET
        usage_posted_at = CURRENT_TIMESTAMP,
        usage_posted_by = p_recorded_by
    WHERE pos_sale_id = p_pos_sale_id
      AND usage_posted_at IS NULL;
END;
$$;

CREATE FUNCTION post_pos_usage_for_date(
    p_sale_date DATE,
    p_recorded_by TEXT
)
RETURNS TABLE (movement_id BIGINT)
LANGUAGE plpgsql
AS $$
DECLARE
    v_pos_sale_id BIGINT;
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pos_sales AS ps
        WHERE ps.sale_date = p_sale_date
          AND NOT EXISTS (
              SELECT 1
              FROM recipes AS r
              WHERE r.menu_item_id = ps.menu_item_id
          )
    ) THEN
        RAISE EXCEPTION 'At least one POS sale on % has no recipe', p_sale_date;
    END IF;

    FOR v_pos_sale_id IN
        SELECT ps.pos_sale_id
        FROM pos_sales AS ps
        WHERE ps.sale_date = p_sale_date
        ORDER BY ps.pos_sale_id
    LOOP
        RETURN QUERY
        SELECT posted.movement_id
        FROM post_pos_sale_usage(v_pos_sale_id, p_recorded_by) AS posted;
    END LOOP;
END;
$$;

CREATE FUNCTION prevent_posted_pos_sale_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' AND OLD.usage_posted_at IS NOT NULL THEN
        RAISE EXCEPTION
            'Posted POS sales cannot be deleted; create an inventory adjustment instead';
    END IF;

    IF TG_OP = 'UPDATE'
       AND OLD.usage_posted_at IS NOT NULL
       AND (
           NEW.sale_date IS DISTINCT FROM OLD.sale_date
           OR NEW.menu_item_id IS DISTINCT FROM OLD.menu_item_id
           OR NEW.quantity_sold IS DISTINCT FROM OLD.quantity_sold
           OR NEW.unit_price IS DISTINCT FROM OLD.unit_price
       ) THEN
        RAISE EXCEPTION
            'Posted POS sale quantities cannot be changed; create an inventory adjustment instead';
    END IF;

    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE TRIGGER pos_sales_protect_posted_source
BEFORE UPDATE OR DELETE ON pos_sales
FOR EACH ROW
EXECUTE FUNCTION prevent_posted_pos_sale_mutation();

COMMIT;
