BEGIN;

SET search_path TO cafe_stock_manage, public;

DO $$
DECLARE
    v_last_sale_date DATE;
BEGIN
    SELECT MAX(sale_date) INTO v_last_sale_date FROM pos_daily_summary;

    IF (SELECT COUNT(*) FROM forecast_daily_sales) <> 30 THEN
        RAISE EXCEPTION 'Expected a 30-day sales forecast';
    END IF;

    IF (SELECT MIN(forecast_date) FROM forecast_daily_sales) <> v_last_sale_date + 1 THEN
        RAISE EXCEPTION 'Forecast must begin after the last observed sales day';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM forecast_daily_sales
        WHERE revenue_lower_bound > forecast_revenue
           OR forecast_revenue > revenue_upper_bound
           OR forecast_items_sold < 0
    ) THEN
        RAISE EXCEPTION 'Forecast bounds or item quantity are invalid';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM inventory_depletion_forecast
        WHERE average_daily_depletion < 0
    ) THEN
        RAISE EXCEPTION 'Inventory depletion rate cannot be negative';
    END IF;
END;
$$;

ROLLBACK;
