BEGIN;

SET search_path TO cafe_stock_manage, public;

ALTER TABLE products
    ADD COLUMN safety_stock_inventory_qty NUMERIC(14, 4) NOT NULL DEFAULT 0;

ALTER TABLE products
    ADD CONSTRAINT products_safety_stock_nonnegative
    CHECK (safety_stock_inventory_qty >= 0);

UPDATE products
SET safety_stock_inventory_qty = CASE product_id
    WHEN 'MILK_FULL' THEN 5
    WHEN 'MILK_SKIM' THEN 1
    WHEN 'MILK_ALMOND' THEN 2
    WHEN 'MILK_OAT' THEN 3
    WHEN 'MILK_SOY' THEN 2
    WHEN 'MILK_LACTOSE_FREE' THEN 1
    WHEN 'COFFEE_REGULAR' THEN 1
    WHEN 'CROISSANT' THEN 5
    WHEN 'EGGS' THEN 25
    ELSE safety_stock_inventory_qty
END;

CREATE VIEW reorder_recommendations AS
WITH activity_anchor AS (
    SELECT COALESCE(MAX(movement_datetime)::DATE, CURRENT_DATE) AS anchor_date
    FROM inventory_movements
),
recent_consumption AS (
    SELECT
        im.product_id,
        SUM(-im.quantity_change)::NUMERIC(14, 4) AS consumed_quantity
    FROM inventory_movements AS im
    CROSS JOIN activity_anchor AS aa
    WHERE im.movement_type IN ('USE', 'WASTE')
      AND im.movement_datetime::DATE > aa.anchor_date - 14
      AND im.movement_datetime::DATE <= aa.anchor_date
    GROUP BY im.product_id
),
open_orders AS (
    SELECT
        poi.product_id,
        SUM(poi.ordered_quantity * p.pack_size)::NUMERIC(14, 4) AS on_order_quantity
    FROM purchase_order_items AS poi
    JOIN purchase_orders AS po ON po.po_id = poi.po_id
    JOIN products AS p ON p.product_id = poi.product_id
    WHERE po.order_status IN ('DRAFT', 'SUBMITTED', 'PARTIALLY_RECEIVED')
      AND (po.order_status = 'DRAFT' OR po.expected_delivery_date >= CURRENT_DATE)
    GROUP BY poi.product_id
),
planning_base AS (
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        p.supplier_id,
        s.supplier_name,
        p.inventory_unit,
        p.order_unit,
        p.pack_size,
        ib.current_quantity,
        COALESCE(oo.on_order_quantity, 0)::NUMERIC(14, 4) AS on_order_quantity,
        (COALESCE(rc.consumed_quantity, 0) / 14.0)::NUMERIC(14, 4)
            AS average_daily_usage,
        COALESCE(
            s.default_lead_time_days,
            CEIL(p.typical_order_frequency_days)::INTEGER,
            1
        ) AS lead_time_days,
        p.safety_stock_inventory_qty,
        p.reorder_point_inventory_qty,
        COALESCE(p.typical_order_frequency_days, 1)::NUMERIC(8, 2)
            AS review_period_days,
        COALESCE(p.typical_order_qty, 1)::NUMERIC(14, 4) AS minimum_order_quantity,
        aa.anchor_date
    FROM products AS p
    JOIN suppliers AS s ON s.supplier_id = p.supplier_id
    JOIN inventory_balance AS ib ON ib.product_id = p.product_id
    CROSS JOIN activity_anchor AS aa
    LEFT JOIN recent_consumption AS rc ON rc.product_id = p.product_id
    LEFT JOIN open_orders AS oo ON oo.product_id = p.product_id
    WHERE p.is_active AND s.is_active
),
planning AS (
    SELECT
        pb.*,
        (
            pb.current_quantity + pb.on_order_quantity
            - pb.average_daily_usage * pb.lead_time_days
        )::NUMERIC(14, 4) AS projected_on_delivery,
        (
            pb.average_daily_usage * (pb.lead_time_days + pb.review_period_days)
            + pb.safety_stock_inventory_qty
        )::NUMERIC(14, 4) AS target_inventory_quantity
    FROM planning_base AS pb
),
scheduled AS (
    SELECT
        pl.*,
        COALESCE(nd.delivery_date, CURRENT_DATE + pl.lead_time_days)
            AS expected_delivery_date
    FROM planning AS pl
    LEFT JOIN LATERAL (
        SELECT candidate.day::DATE AS delivery_date
        FROM GENERATE_SERIES(
            CURRENT_DATE + pl.lead_time_days,
            CURRENT_DATE + pl.lead_time_days + 14,
            INTERVAL '1 day'
        ) AS candidate(day)
        LEFT JOIN supplier_delivery_schedule AS sds
          ON sds.supplier_id = pl.supplier_id
         AND sds.weekday = EXTRACT(DOW FROM candidate.day)::SMALLINT
        WHERE COALESCE(sds.delivery_available, TRUE)
        ORDER BY candidate.day
        LIMIT 1
    ) AS nd ON TRUE
),
recommended AS (
    SELECT
        scheduled.*,
        CEIL(
            GREATEST(
                0,
                scheduled.target_inventory_quantity
                - scheduled.projected_on_delivery
            ) / scheduled.pack_size
        )::NUMERIC(14, 4) AS calculated_order_quantity
    FROM scheduled
)
SELECT
    product_id,
    product_name,
    category,
    supplier_id,
    supplier_name,
    inventory_unit,
    order_unit,
    pack_size,
    current_quantity,
    on_order_quantity,
    average_daily_usage,
    lead_time_days,
    safety_stock_inventory_qty,
    reorder_point_inventory_qty,
    projected_on_delivery,
    target_inventory_quantity,
    CASE
        WHEN calculated_order_quantity > 0
        THEN GREATEST(calculated_order_quantity, minimum_order_quantity)
        ELSE 0
    END::NUMERIC(14, 4) AS recommended_order_quantity,
    expected_delivery_date,
    CASE
        WHEN current_quantity < 0 THEN 'CRITICAL'
        WHEN reorder_point_inventory_qty IS NOT NULL
         AND current_quantity <= reorder_point_inventory_qty THEN 'ORDER_NOW'
        WHEN projected_on_delivery <= safety_stock_inventory_qty THEN 'REVIEW'
        ELSE 'PLANNED'
    END AS urgency
FROM recommended;

COMMENT ON VIEW reorder_recommendations IS
    'Fourteen-day consumption-based replenishment plan expressed in each product order unit.';

COMMIT;
