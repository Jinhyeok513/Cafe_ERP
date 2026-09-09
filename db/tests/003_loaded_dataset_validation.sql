\set ON_ERROR_STOP on

SET search_path TO cafe_stock_manage, public;

DO $$
DECLARE
    v_issue_count INTEGER;
    v_import_count INTEGER;
    v_movement_count INTEGER;
    v_negative_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_import_count FROM dataset_imports;
    IF v_import_count <> 1 THEN
        RAISE EXCEPTION 'Expected one dataset import, found %', v_import_count;
    END IF;

    SELECT COUNT(*) INTO v_issue_count FROM data_quality_issues;
    IF v_issue_count <> 0 THEN
        RAISE EXCEPTION 'Expected zero data quality issues, found %', v_issue_count;
    END IF;

    SELECT COUNT(*) INTO v_movement_count FROM inventory_movements;
    IF v_movement_count = 0 THEN
        RAISE EXCEPTION 'Expected imported inventory movements';
    END IF;

    SELECT COUNT(*)
    INTO v_negative_count
    FROM inventory_movement_timeline
    WHERE running_quantity < 0;
    IF v_negative_count <> 0 THEN
        RAISE EXCEPTION 'Expected no negative running inventory, found %', v_negative_count;
    END IF;
END;
$$;
