BEGIN;

SET search_path TO cafe_stock_manage, public;

CREATE VIEW pos_sale_posting_status AS
SELECT
    ps.pos_sale_id,
    ps.source_key,
    ps.sale_date,
    ps.menu_item_id,
    mi.menu_item_name,
    mi.menu_category,
    ps.quantity_sold,
    ps.unit_price,
    ps.gross_revenue,
    (
        SELECT COUNT(*)
        FROM recipe_inventory_requirements AS rir
        WHERE rir.menu_item_id = ps.menu_item_id
    ) AS expected_movement_count,
    (
        SELECT COUNT(DISTINCT im.product_id)
        FROM inventory_movements AS im
        WHERE im.source_type = 'POS_SALE'
          AND (im.source_id = ps.pos_sale_id::TEXT OR im.source_id = ps.source_key)
    ) AS actual_movement_count,
    CASE
        WHEN (
            SELECT COUNT(*)
            FROM recipe_inventory_requirements AS rir
            WHERE rir.menu_item_id = ps.menu_item_id
        ) = 0 THEN 'MISSING_RECIPE'
        WHEN (
            SELECT COUNT(*)
            FROM recipe_inventory_requirements AS rir
            WHERE rir.menu_item_id = ps.menu_item_id
        ) = (
            SELECT COUNT(DISTINCT im.product_id)
            FROM inventory_movements AS im
            WHERE im.source_type = 'POS_SALE'
              AND (im.source_id = ps.pos_sale_id::TEXT OR im.source_id = ps.source_key)
        ) THEN 'POSTED'
        ELSE 'PENDING'
    END AS usage_status
FROM pos_sales AS ps
JOIN menu_items AS mi ON mi.menu_item_id = ps.menu_item_id;

CREATE VIEW pos_daily_summary AS
SELECT
    sale_date,
    COUNT(*) AS menu_lines,
    SUM(quantity_sold)::BIGINT AS items_sold,
    SUM(gross_revenue)::NUMERIC(14, 2) AS gross_revenue,
    COUNT(*) FILTER (WHERE usage_status = 'POSTED') AS posted_lines,
    COUNT(*) FILTER (WHERE usage_status = 'PENDING') AS pending_lines,
    COUNT(*) FILTER (WHERE usage_status = 'MISSING_RECIPE') AS missing_recipe_lines
FROM pos_sale_posting_status
GROUP BY sale_date;

CREATE VIEW pos_daily_inventory_usage AS
SELECT
    ps.sale_date,
    im.product_id,
    p.product_name,
    p.category,
    p.inventory_unit,
    SUM(-im.quantity_change)::NUMERIC(14, 4) AS usage_quantity,
    COUNT(DISTINCT ps.menu_item_id) AS contributing_menu_items
FROM pos_sales AS ps
JOIN inventory_movements AS im
  ON im.source_type = 'POS_SALE'
 AND (im.source_id = ps.pos_sale_id::TEXT OR im.source_id = ps.source_key)
JOIN products AS p ON p.product_id = im.product_id
WHERE im.movement_type = 'USE'
GROUP BY ps.sale_date, im.product_id, p.product_name, p.category, p.inventory_unit;

COMMENT ON VIEW pos_sale_posting_status IS
    'Compares recipe ingredient count with immutable POS usage movements for every sale total.';

COMMIT;
