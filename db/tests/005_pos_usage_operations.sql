BEGIN;

SET search_path TO cafe_stock_manage, public;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pos_sale_posting_status
        WHERE usage_status <> 'POSTED'
    ) THEN
        RAISE EXCEPTION 'Loaded POS sales must have complete recipe-derived movements';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pos_daily_inventory_usage
        WHERE usage_quantity <= 0
    ) THEN
        RAISE EXCEPTION 'Daily POS inventory usage must be positive in reporting views';
    END IF;

    IF (SELECT COUNT(*) FROM pos_daily_summary) <> 30 THEN
        RAISE EXCEPTION 'Expected 30 POS daily summaries';
    END IF;
END;
$$;

ROLLBACK;
