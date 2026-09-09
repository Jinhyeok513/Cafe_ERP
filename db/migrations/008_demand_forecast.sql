BEGIN;

SET search_path TO cafe_stock_manage, public;

CREATE VIEW forecast_daily_sales AS
WITH anchor AS (
    SELECT MAX(sale_date) AS last_sale_date
    FROM pos_daily_summary
),
history AS (
    SELECT
        pds.sale_date,
        EXTRACT(DOW FROM pds.sale_date)::INTEGER AS weekday,
        pds.items_sold,
        pds.gross_revenue
    FROM pos_daily_summary AS pds
    CROSS JOIN anchor AS a
    WHERE pds.sale_date > a.last_sale_date - 28
),
weekday_stats AS (
    SELECT
        weekday,
        AVG(items_sold)::NUMERIC AS average_items,
        AVG(gross_revenue)::NUMERIC AS average_revenue,
        STDDEV_POP(gross_revenue)::NUMERIC AS revenue_deviation
    FROM history
    GROUP BY weekday
),
overall_stats AS (
    SELECT
        AVG(items_sold)::NUMERIC AS average_items,
        AVG(gross_revenue)::NUMERIC AS average_revenue,
        STDDEV_POP(gross_revenue)::NUMERIC AS revenue_deviation
    FROM history
),
trend AS (
    SELECT LEAST(
        1.15,
        GREATEST(
            0.85,
            COALESCE(
                AVG(gross_revenue) FILTER (
                    WHERE sale_date > (SELECT last_sale_date FROM anchor) - 7
                ) / NULLIF(
                    AVG(gross_revenue) FILTER (
                        WHERE sale_date > (SELECT last_sale_date FROM anchor) - 14
                          AND sale_date <= (SELECT last_sale_date FROM anchor) - 7
                    ),
                    0
                ),
                1
            )
        )
    )::NUMERIC AS trend_factor
    FROM history
),
future_dates AS (
    SELECT (a.last_sale_date + offset_day)::DATE AS forecast_date
    FROM anchor AS a
    CROSS JOIN GENERATE_SERIES(1, 30) AS offsets(offset_day)
)
SELECT
    fd.forecast_date,
    TO_CHAR(fd.forecast_date, 'Dy') AS weekday_name,
    ROUND(COALESCE(ws.average_items, os.average_items) * t.trend_factor)::BIGINT
        AS forecast_items_sold,
    ROUND(COALESCE(ws.average_revenue, os.average_revenue) * t.trend_factor, 2)
        AS forecast_revenue,
    GREATEST(
        0,
        ROUND(
            (COALESCE(ws.average_revenue, os.average_revenue)
                - COALESCE(ws.revenue_deviation, os.revenue_deviation * 0.5, 0))
            * t.trend_factor,
            2
        )
    ) AS revenue_lower_bound,
    ROUND(
        (COALESCE(ws.average_revenue, os.average_revenue)
            + COALESCE(ws.revenue_deviation, os.revenue_deviation * 0.5, 0))
        * t.trend_factor,
        2
    ) AS revenue_upper_bound,
    t.trend_factor,
    'WEEKDAY_BASELINE'::TEXT AS forecast_method
FROM future_dates AS fd
CROSS JOIN overall_stats AS os
CROSS JOIN trend AS t
LEFT JOIN weekday_stats AS ws
  ON ws.weekday = EXTRACT(DOW FROM fd.forecast_date)::INTEGER
ORDER BY fd.forecast_date;

CREATE VIEW inventory_depletion_forecast AS
WITH anchor AS (
    SELECT COALESCE(MAX(movement_datetime)::DATE, CURRENT_DATE) AS activity_date
    FROM inventory_movements
),
pos_usage AS (
    SELECT
        pdiu.product_id,
        (SUM(pdiu.usage_quantity) / 14.0)::NUMERIC(14, 4) AS daily_pos_usage
    FROM pos_daily_inventory_usage AS pdiu
    CROSS JOIN anchor AS a
    WHERE pdiu.sale_date > a.activity_date - 14
      AND pdiu.sale_date <= a.activity_date
    GROUP BY pdiu.product_id
),
waste_usage AS (
    SELECT
        im.product_id,
        (SUM(-im.quantity_change) / 14.0)::NUMERIC(14, 4) AS daily_waste
    FROM inventory_movements AS im
    CROSS JOIN anchor AS a
    WHERE im.movement_type = 'WASTE'
      AND im.movement_datetime::DATE > a.activity_date - 14
      AND im.movement_datetime::DATE <= a.activity_date
    GROUP BY im.product_id
),
open_orders AS (
    SELECT
        poi.product_id,
        SUM(poi.ordered_quantity * p.pack_size)::NUMERIC(14, 4) AS on_order_quantity
    FROM purchase_order_items AS poi
    JOIN purchase_orders AS po ON po.po_id = poi.po_id
    JOIN products AS p ON p.product_id = poi.product_id
    CROSS JOIN anchor AS a
    WHERE po.order_status IN ('DRAFT', 'SUBMITTED', 'PARTIALLY_RECEIVED')
      AND po.expected_delivery_date > a.activity_date
    GROUP BY poi.product_id
),
base AS (
    SELECT
        p.product_id,
        p.product_name,
        p.category,
        p.inventory_unit,
        p.supplier_id,
        s.supplier_name,
        COALESCE(s.default_lead_time_days, 1) AS lead_time_days,
        ib.current_quantity,
        COALESCE(oo.on_order_quantity, 0)::NUMERIC(14, 4) AS on_order_quantity,
        (COALESCE(pu.daily_pos_usage, 0) + COALESCE(wu.daily_waste, 0))::NUMERIC(14, 4)
            AS average_daily_depletion,
        a.activity_date
    FROM products AS p
    JOIN suppliers AS s ON s.supplier_id = p.supplier_id
    JOIN inventory_balance AS ib ON ib.product_id = p.product_id
    CROSS JOIN anchor AS a
    LEFT JOIN pos_usage AS pu ON pu.product_id = p.product_id
    LEFT JOIN waste_usage AS wu ON wu.product_id = p.product_id
    LEFT JOIN open_orders AS oo ON oo.product_id = p.product_id
    WHERE p.is_active
)
SELECT
    product_id,
    product_name,
    category,
    inventory_unit,
    supplier_id,
    supplier_name,
    lead_time_days,
    current_quantity,
    on_order_quantity,
    average_daily_depletion,
    CASE
        WHEN average_daily_depletion > 0
        THEN ROUND((current_quantity + on_order_quantity) / average_daily_depletion, 1)
        ELSE NULL
    END AS days_of_cover,
    (current_quantity + on_order_quantity - average_daily_depletion * 7)::NUMERIC(14, 4)
        AS projected_quantity_7_days,
    (current_quantity + on_order_quantity - average_daily_depletion * 14)::NUMERIC(14, 4)
        AS projected_quantity_14_days,
    CASE
        WHEN average_daily_depletion > 0
        THEN activity_date + GREATEST(
            0,
            FLOOR((current_quantity + on_order_quantity) / average_daily_depletion)::INTEGER
        )
        ELSE NULL
    END AS expected_stockout_date,
    CASE
        WHEN current_quantity <= 0 THEN 'STOCKOUT'
        WHEN average_daily_depletion = 0 THEN 'NO_USAGE'
        WHEN (current_quantity + on_order_quantity) / average_daily_depletion <= lead_time_days
            THEN 'CRITICAL'
        WHEN (current_quantity + on_order_quantity) / average_daily_depletion <= 7
            THEN 'WATCH'
        ELSE 'HEALTHY'
    END AS risk_status
FROM base;

COMMENT ON VIEW forecast_daily_sales IS
    'Transparent weekday baseline with a capped recent trend factor and empirical revenue range.';
COMMENT ON VIEW inventory_depletion_forecast IS
    'Fourteen-day POS usage and waste run-rate projected in each product inventory unit.';

COMMIT;
