BEGIN;

CREATE SCHEMA IF NOT EXISTS cafe_stock_manage;
SET search_path TO cafe_stock_manage, public;

CREATE TABLE suppliers (
    supplier_id TEXT PRIMARY KEY,
    supplier_name TEXT NOT NULL,
    supplier_type TEXT NOT NULL,
    default_lead_time_days INTEGER,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    CONSTRAINT suppliers_lead_time_nonnegative
        CHECK (default_lead_time_days IS NULL OR default_lead_time_days >= 0)
);

CREATE TABLE products (
    product_id TEXT PRIMARY KEY,
    product_name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    inventory_unit TEXT NOT NULL,
    order_unit TEXT NOT NULL,
    pack_size NUMERIC(14, 4) NOT NULL DEFAULT 1,
    content_quantity_per_inventory_unit NUMERIC(14, 4),
    content_unit TEXT,
    supplier_id TEXT REFERENCES suppliers (supplier_id),
    perishable BOOLEAN NOT NULL DEFAULT FALSE,
    shelf_life_days INTEGER,
    typical_order_frequency_days NUMERIC(8, 2),
    typical_order_qty NUMERIC(14, 4),
    reorder_point_inventory_qty NUMERIC(14, 4),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT products_pack_size_positive CHECK (pack_size > 0),
    CONSTRAINT products_shelf_life_positive
        CHECK (shelf_life_days IS NULL OR shelf_life_days > 0),
    CONSTRAINT products_order_frequency_positive
        CHECK (
            typical_order_frequency_days IS NULL
            OR typical_order_frequency_days > 0
        ),
    CONSTRAINT products_typical_order_qty_positive
        CHECK (typical_order_qty IS NULL OR typical_order_qty > 0),
    CONSTRAINT products_reorder_point_nonnegative
        CHECK (
            reorder_point_inventory_qty IS NULL
            OR reorder_point_inventory_qty >= 0
        ),
    CONSTRAINT products_content_pair_complete
        CHECK (
            (content_quantity_per_inventory_unit IS NULL AND content_unit IS NULL)
            OR (
                content_quantity_per_inventory_unit > 0
                AND content_unit IS NOT NULL
            )
        )
);

COMMENT ON COLUMN products.inventory_unit IS
    'Unit used for stock counts and inventory movements, such as bottle, carton, bag or each.';
COMMENT ON COLUMN products.pack_size IS
    'Number of inventory units in one order unit. Example: one egg tray contains 25 each.';
COMMENT ON COLUMN products.content_quantity_per_inventory_unit IS
    'Physical content held by one inventory unit for recipe conversion, such as 1.5 litres per bottle.';

CREATE TABLE supplier_delivery_schedule (
    supplier_id TEXT NOT NULL REFERENCES suppliers (supplier_id),
    weekday SMALLINT NOT NULL,
    delivery_available BOOLEAN NOT NULL,
    order_cutoff_time TIME,
    PRIMARY KEY (supplier_id, weekday),
    CONSTRAINT supplier_schedule_valid_weekday CHECK (weekday BETWEEN 0 AND 6)
);

CREATE TABLE purchase_orders (
    po_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    supplier_id TEXT NOT NULL REFERENCES suppliers (supplier_id),
    order_datetime TIMESTAMPTZ NOT NULL,
    expected_delivery_date DATE NOT NULL,
    order_status TEXT NOT NULL,
    ordered_by TEXT NOT NULL,
    notes TEXT,
    CONSTRAINT purchase_orders_status_valid
        CHECK (order_status IN ('DRAFT', 'SUBMITTED', 'PARTIALLY_RECEIVED', 'RECEIVED', 'CANCELLED')),
    CONSTRAINT purchase_orders_supplier_pair UNIQUE (po_id, supplier_id)
);

CREATE TABLE purchase_order_items (
    po_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    po_id BIGINT NOT NULL REFERENCES purchase_orders (po_id),
    product_id TEXT NOT NULL REFERENCES products (product_id),
    ordered_quantity NUMERIC(14, 4) NOT NULL,
    order_unit TEXT NOT NULL,
    unit_cost NUMERIC(14, 2),
    CONSTRAINT purchase_order_items_quantity_positive CHECK (ordered_quantity > 0),
    CONSTRAINT purchase_order_items_cost_nonnegative
        CHECK (unit_cost IS NULL OR unit_cost >= 0),
    CONSTRAINT purchase_order_items_one_product_per_order UNIQUE (po_id, product_id),
    CONSTRAINT purchase_order_items_id_product_pair UNIQUE (po_item_id, product_id)
);

CREATE TABLE goods_receipts (
    receipt_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    po_id BIGINT NOT NULL,
    supplier_id TEXT NOT NULL,
    received_datetime TIMESTAMPTZ NOT NULL,
    invoice_number TEXT,
    received_by TEXT NOT NULL,
    receipt_status TEXT NOT NULL,
    notes TEXT,
    CONSTRAINT goods_receipts_po_supplier_fk
        FOREIGN KEY (po_id, supplier_id)
        REFERENCES purchase_orders (po_id, supplier_id),
    CONSTRAINT goods_receipts_status_valid
        CHECK (receipt_status IN ('DRAFT', 'CHECKED', 'POSTED', 'REJECTED'))
);

CREATE TABLE goods_receipt_items (
    receipt_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    receipt_id BIGINT NOT NULL REFERENCES goods_receipts (receipt_id),
    po_item_id BIGINT NOT NULL,
    product_id TEXT NOT NULL,
    invoice_quantity NUMERIC(14, 4) NOT NULL,
    received_quantity NUMERIC(14, 4) NOT NULL,
    damaged_quantity NUMERIC(14, 4) NOT NULL DEFAULT 0,
    accepted_quantity NUMERIC(14, 4) NOT NULL,
    wrong_item_flag BOOLEAN NOT NULL DEFAULT FALSE,
    discrepancy_reason TEXT NOT NULL DEFAULT 'NONE',
    notes TEXT,
    CONSTRAINT goods_receipt_items_po_product_fk
        FOREIGN KEY (po_item_id, product_id)
        REFERENCES purchase_order_items (po_item_id, product_id),
    CONSTRAINT goods_receipt_items_one_po_line_per_receipt
        UNIQUE (receipt_id, po_item_id),
    CONSTRAINT goods_receipt_items_quantities_nonnegative
        CHECK (
            invoice_quantity >= 0
            AND received_quantity >= 0
            AND damaged_quantity >= 0
            AND accepted_quantity >= 0
        ),
    CONSTRAINT goods_receipt_items_accepted_within_received
        CHECK (accepted_quantity <= received_quantity - damaged_quantity),
    CONSTRAINT goods_receipt_items_discrepancy_reason_valid
        CHECK (
            discrepancy_reason IN (
                'NONE',
                'SHORT_DELIVERY',
                'MISSING_ITEM',
                'WRONG_PRODUCT',
                'DAMAGED',
                'OTHER'
            )
        ),
    CONSTRAINT goods_receipt_items_missing_item_consistent
        CHECK (
            discrepancy_reason <> 'MISSING_ITEM'
            OR (received_quantity = 0 AND accepted_quantity = 0)
        ),
    CONSTRAINT goods_receipt_items_short_delivery_consistent
        CHECK (
            discrepancy_reason <> 'SHORT_DELIVERY'
            OR received_quantity < invoice_quantity
        ),
    CONSTRAINT goods_receipt_items_wrong_product_consistent
        CHECK (NOT wrong_item_flag OR accepted_quantity = 0)
);

COMMIT;
