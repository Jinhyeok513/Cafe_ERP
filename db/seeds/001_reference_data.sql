BEGIN;

SET search_path TO cafe_stock_manage, public;

INSERT INTO suppliers (
    supplier_id,
    supplier_name,
    supplier_type,
    default_lead_time_days,
    notes
)
VALUES
    ('SUP_A', 'Bakery Supplier', 'SCHEDULED', 1, 'Actual supplier name remains anonymous.'),
    ('SUP_B', 'Milk Supplier', 'SCHEDULED', 1, 'Sunday delivery is unavailable.'),
    ('SUP_C', 'Food Supplier', 'SCHEDULED', NULL, 'Fresh food delivery is usually Monday, Wednesday and Saturday.'),
    ('SUP_D', 'Coffee Supplier', 'SCHEDULED', NULL, 'Exact lead time remains TBD.'),
    ('OWNER', 'Owner Purchase', 'MANUAL', 0, 'Direct purchases outside the regular supplier schedule.')
ON CONFLICT (supplier_id) DO NOTHING;

INSERT INTO products (
    product_id,
    product_name,
    category,
    inventory_unit,
    order_unit,
    pack_size,
    content_quantity_per_inventory_unit,
    content_unit,
    supplier_id,
    perishable,
    shelf_life_days,
    typical_order_frequency_days,
    typical_order_qty,
    reorder_point_inventory_qty
)
VALUES
    ('MILK_FULL', 'Full Cream Milk', 'MILK', 'bottle', 'bottle', 1, 1.5, 'litre', 'SUP_B', TRUE, NULL, 1, 15, NULL),
    ('MILK_SKIM', 'Skim Milk', 'MILK', 'bottle', 'bottle', 1, 1.5, 'litre', 'SUP_B', TRUE, NULL, 1, 3, NULL),
    ('MILK_ALMOND', 'Almond Milk', 'MILK', 'carton', 'carton', 1, 1, 'litre', 'SUP_B', TRUE, NULL, 2, 8, 3),
    ('MILK_OAT', 'Oat Milk', 'MILK', 'carton', 'carton', 1, 1, 'litre', 'SUP_B', TRUE, NULL, 2, 8, 3),
    ('MILK_SOY', 'Soy Milk', 'MILK', 'carton', 'carton', 1, 1, 'litre', 'SUP_B', TRUE, NULL, 2, 8, 3),
    ('MILK_LACTOSE_FREE', 'Lactose-Free Milk', 'MILK', 'carton', 'carton', 1, 1, 'litre', 'SUP_B', TRUE, NULL, 7, 8, NULL),
    ('COFFEE_REGULAR', 'Regular Coffee Beans', 'COFFEE', 'bag', 'bag', 1, 1, 'kilogram', 'SUP_D', FALSE, NULL, 3, 8, NULL),
    ('CROISSANT', 'Croissant', 'BAKERY', 'each', 'each', 1, NULL, NULL, 'SUP_A', TRUE, 2, 1, 20, NULL),
    ('EGGS', 'Eggs', 'FOOD', 'each', 'tray', 25, NULL, NULL, 'SUP_C', TRUE, NULL, 3, 9, 50)
ON CONFLICT (product_id) DO NOTHING;

INSERT INTO supplier_delivery_schedule (
    supplier_id,
    weekday,
    delivery_available,
    order_cutoff_time
)
SELECT
    supplier_id,
    weekday,
    CASE
        WHEN supplier_id IN ('SUP_A', 'SUP_B') THEN weekday <> 0
        WHEN supplier_id = 'SUP_C' THEN weekday IN (1, 3, 6)
        ELSE TRUE
    END,
    CASE WHEN supplier_id = 'SUP_A' THEN TIME '14:00' ELSE NULL END
FROM (
    SELECT supplier_id
    FROM suppliers
    WHERE supplier_id IN ('SUP_A', 'SUP_B', 'SUP_C')
) AS known_suppliers
CROSS JOIN GENERATE_SERIES(0, 6) AS weekdays(weekday)
ON CONFLICT (supplier_id, weekday) DO NOTHING;

COMMIT;
