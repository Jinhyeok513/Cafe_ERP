"""Read-only PostgreSQL queries for cafe inventory operations."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


class InventoryRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def fetch_all(
        self,
        query: str,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        with self.pool.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query, parameters)
                return list(cursor.fetchall())

    def fetch_one(
        self,
        query: str,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        rows = self.fetch_all(query, parameters)
        return rows[0] if rows else None

    def health(self) -> dict[str, Any]:
        row = self.fetch_one(
            """
            SELECT
                TRUE AS database_connected,
                di.scenario,
                di.dataset_sha256,
                di.imported_at
            FROM cafe_stock_manage.dataset_imports AS di
            ORDER BY di.imported_at DESC
            LIMIT 1
            """
        )
        return row or {
            "database_connected": True,
            "scenario": None,
            "dataset_sha256": None,
            "imported_at": None,
        }

    def inventory(
        self,
        status: str | None,
        search: str | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        parameters: list[Any] = []
        if status is not None:
            conditions.append("stock_status = %s")
            parameters.append(status)
        if search is not None:
            conditions.append("(product_id ILIKE %s OR product_name ILIKE %s)")
            pattern = f"%{search}%"
            parameters.extend((pattern, pattern))
        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        parameters.extend((limit, offset))
        return self.fetch_all(
            f"""
            SELECT
                product_id,
                product_name,
                category,
                inventory_unit,
                current_quantity,
                reorder_point_inventory_qty,
                stock_status
            FROM cafe_stock_manage.current_inventory_status
            WHERE {where_clause}
            ORDER BY
                CASE stock_status
                    WHEN 'NEGATIVE_STOCK' THEN 1
                    WHEN 'REORDER_DUE' THEN 2
                    WHEN 'IN_STOCK' THEN 3
                    ELSE 4
                END,
                product_name
            LIMIT %s OFFSET %s
            """,
            tuple(parameters),
        )

    def inventory_product(self, product_id: str) -> dict[str, Any] | None:
        return self.fetch_one(
            """
            SELECT
                product_id,
                product_name,
                category,
                inventory_unit,
                current_quantity,
                reorder_point_inventory_qty,
                stock_status
            FROM cafe_stock_manage.current_inventory_status
            WHERE product_id = %s
            """,
            (product_id,),
        )

    def movements(
        self,
        product_id: str,
        movement_type: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        movement_filter = ""
        parameters: list[Any] = [product_id]
        if movement_type is not None:
            movement_filter = "AND movement_type = %s"
            parameters.append(movement_type)
        parameters.append(limit)
        return self.fetch_all(
            f"""
            SELECT
                movement_id,
                movement_source_key,
                product_id,
                product_name,
                inventory_unit,
                movement_datetime,
                movement_type,
                quantity_change,
                running_quantity,
                source_type,
                source_id,
                reason_code,
                recorded_by
            FROM cafe_stock_manage.inventory_movement_timeline
            WHERE product_id = %s
              {movement_filter}
            ORDER BY movement_datetime DESC, movement_id DESC
            LIMIT %s
            """,
            tuple(parameters),
        )

    def discrepancies(
        self,
        reason: str | None,
        supplier_id: str | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        conditions = ["gri.discrepancy_reason <> 'NONE'"]
        parameters: list[Any] = []
        if reason is not None:
            conditions.append("gri.discrepancy_reason = %s")
            parameters.append(reason)
        if supplier_id is not None:
            conditions.append("gr.supplier_id = %s")
            parameters.append(supplier_id)
        where_clause = " AND ".join(conditions)
        parameters.extend((limit, offset))
        return self.fetch_all(
            f"""
            SELECT
                gr.source_key AS receipt_source_key,
                gr.received_datetime,
                gr.supplier_id,
                gri.source_key AS receipt_item_source_key,
                gri.product_id,
                p.product_name,
                p.order_unit,
                gri.invoice_quantity,
                gri.received_quantity,
                gri.damaged_quantity,
                gri.accepted_quantity,
                gri.wrong_item_flag,
                gri.discrepancy_reason
            FROM cafe_stock_manage.goods_receipt_items AS gri
            JOIN cafe_stock_manage.goods_receipts AS gr
              ON gr.receipt_id = gri.receipt_id
            JOIN cafe_stock_manage.products AS p
              ON p.product_id = gri.product_id
            WHERE {where_clause}
            ORDER BY gr.received_datetime DESC, gri.receipt_item_id DESC
            LIMIT %s OFFSET %s
            """,
            tuple(parameters),
        )

    def stocktake_accuracy(
        self,
        date_from: date | None,
        date_to: date | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        parameters: list[Any] = []
        if date_from is not None:
            conditions.append("stocktake_date >= %s")
            parameters.append(date_from)
        if date_to is not None:
            conditions.append("stocktake_date <= %s")
            parameters.append(date_to)
        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        parameters.append(limit)
        return self.fetch_all(
            f"""
            SELECT
                stocktake_id,
                source_key,
                stocktake_date,
                products_counted,
                products_matched,
                products_with_variance,
                inventory_accuracy_percent,
                absolute_variance_quantity
            FROM cafe_stock_manage.stocktake_accuracy_daily
            WHERE {where_clause}
            ORDER BY stocktake_date DESC
            LIMIT %s
            """,
            tuple(parameters),
        )

    def kpis(self) -> dict[str, Any]:
        row = self.fetch_one(
            """
            SELECT
                (SELECT COUNT(*) FROM cafe_stock_manage.products WHERE is_active)
                    AS active_products,
                (
                    SELECT COUNT(*)
                    FROM cafe_stock_manage.current_inventory_status
                    WHERE stock_status = 'REORDER_DUE'
                ) AS reorder_due_products,
                (
                    SELECT COUNT(*)
                    FROM cafe_stock_manage.current_inventory_status
                    WHERE stock_status = 'NEGATIVE_STOCK'
                ) AS negative_stock_products,
                (
                    SELECT COUNT(*)
                    FROM cafe_stock_manage.goods_receipt_items
                ) AS receipt_lines,
                (
                    SELECT COUNT(*)
                    FROM cafe_stock_manage.goods_receipt_items
                    WHERE discrepancy_reason <> 'NONE'
                ) AS discrepancy_lines,
                (
                    SELECT COUNT(*)
                    FROM cafe_stock_manage.inventory_movements
                    WHERE movement_type = 'WASTE'
                ) AS waste_events,
                (
                    SELECT COUNT(*)
                    FROM cafe_stock_manage.inventory_movements
                ) AS movement_count,
                (
                    SELECT inventory_accuracy_percent
                    FROM cafe_stock_manage.stocktake_accuracy_daily
                    ORDER BY stocktake_date DESC
                    LIMIT 1
                ) AS latest_inventory_accuracy_percent,
                (
                    SELECT COUNT(*)
                    FROM cafe_stock_manage.data_quality_issues
                ) AS data_quality_issue_count
            """
        )
        if row is None:
            raise RuntimeError("KPI query returned no row")
        receipt_lines = row["receipt_lines"]
        discrepancy_lines = row["discrepancy_lines"]
        row["receiving_accuracy_percent"] = (
            round(100 * (receipt_lines - discrepancy_lines) / receipt_lines, 2)
            if receipt_lines
            else None
        )
        return row

    def reorder_recommendations(
        self,
        urgency: str | None,
    ) -> list[dict[str, Any]]:
        urgency_filter = ""
        parameters: tuple[Any, ...] = ()
        if urgency is not None:
            urgency_filter = "AND urgency = %s"
            parameters = (urgency,)
        return self.fetch_all(
            f"""
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
                recommended_order_quantity,
                expected_delivery_date,
                urgency
            FROM cafe_stock_manage.reorder_recommendations
            WHERE recommended_order_quantity > 0
              {urgency_filter}
            ORDER BY
                CASE urgency
                    WHEN 'CRITICAL' THEN 1
                    WHEN 'ORDER_NOW' THEN 2
                    WHEN 'REVIEW' THEN 3
                    ELSE 4
                END,
                expected_delivery_date,
                supplier_name,
                product_name
            """,
            parameters,
        )

    def create_draft_purchase_order(
        self,
        supplier_id: str,
        expected_delivery_date: date,
        ordered_by: str,
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        product_ids = [item["product_id"] for item in items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("A product can appear only once in a draft order")

        with self.pool.connection() as connection:
            with connection.transaction():
                with connection.cursor(row_factory=dict_row) as cursor:
                    cursor.execute(
                        """
                        SELECT product_id, product_name, supplier_id, order_unit
                        FROM cafe_stock_manage.products
                        WHERE product_id = ANY(%s) AND is_active
                        """,
                        (product_ids,),
                    )
                    products = {row["product_id"]: row for row in cursor.fetchall()}
                    missing = sorted(set(product_ids) - set(products))
                    if missing:
                        raise ValueError(f"Unknown active products: {', '.join(missing)}")
                    mismatched = [
                        row["product_name"]
                        for row in products.values()
                        if row["supplier_id"] != supplier_id
                    ]
                    if mismatched:
                        raise ValueError(
                            "Products do not belong to the selected supplier: "
                            + ", ".join(sorted(mismatched))
                        )

                    source_key = f"DRAFT-{uuid4()}"
                    cursor.execute(
                        """
                        INSERT INTO cafe_stock_manage.purchase_orders (
                            source_key,
                            supplier_id,
                            order_datetime,
                            expected_delivery_date,
                            order_status,
                            ordered_by,
                            notes
                        )
                        VALUES (%s, %s, CURRENT_TIMESTAMP, %s, 'DRAFT', %s, %s)
                        RETURNING po_id, source_key, order_datetime
                        """,
                        (
                            source_key,
                            supplier_id,
                            expected_delivery_date,
                            ordered_by,
                            "Created from replenishment recommendation",
                        ),
                    )
                    order = cursor.fetchone()
                    if order is None:
                        raise RuntimeError("Draft purchase order insert returned no row")

                    created_items: list[dict[str, Any]] = []
                    for item in items:
                        product = products[item["product_id"]]
                        cursor.execute(
                            """
                            INSERT INTO cafe_stock_manage.purchase_order_items (
                                source_key,
                                po_id,
                                product_id,
                                ordered_quantity,
                                order_unit
                            )
                            VALUES (%s, %s, %s, %s, %s)
                            RETURNING po_item_id, product_id, ordered_quantity, order_unit
                            """,
                            (
                                f"{source_key}-{item['product_id']}",
                                order["po_id"],
                                item["product_id"],
                                item["ordered_quantity"],
                                product["order_unit"],
                            ),
                        )
                        created_item = cursor.fetchone()
                        if created_item is not None:
                            created_items.append(created_item)

        return {
            **order,
            "supplier_id": supplier_id,
            "expected_delivery_date": expected_delivery_date,
            "order_status": "DRAFT",
            "ordered_by": ordered_by,
            "items": created_items,
        }

    def pos_days(self, limit: int) -> list[dict[str, Any]]:
        return self.fetch_all(
            """
            SELECT
                sale_date,
                menu_lines,
                items_sold,
                gross_revenue,
                posted_lines,
                pending_lines,
                missing_recipe_lines
            FROM cafe_stock_manage.pos_daily_summary
            ORDER BY sale_date DESC
            LIMIT %s
            """,
            (limit,),
        )

    def pos_usage(self, sale_date: date | None) -> list[dict[str, Any]]:
        return self.fetch_all(
            """
            SELECT
                sale_date,
                product_id,
                product_name,
                category,
                inventory_unit,
                usage_quantity,
                contributing_menu_items
            FROM cafe_stock_manage.pos_daily_inventory_usage
            WHERE sale_date = COALESCE(
                %s::DATE,
                (SELECT MAX(sale_date) FROM cafe_stock_manage.pos_daily_inventory_usage)
            )
            ORDER BY usage_quantity DESC, product_name
            """,
            (sale_date,),
        )

    def menu_items(self) -> list[dict[str, Any]]:
        return self.fetch_all(
            """
            SELECT
                mi.menu_item_id,
                mi.menu_item_name,
                mi.menu_category,
                mi.selling_price,
                COUNT(r.recipe_id) AS recipe_ingredient_count
            FROM cafe_stock_manage.menu_items AS mi
            LEFT JOIN cafe_stock_manage.recipes AS r
              ON r.menu_item_id = mi.menu_item_id
            WHERE mi.is_active
            GROUP BY mi.menu_item_id
            ORDER BY mi.menu_category, mi.menu_item_name
            """
        )

    def import_pos_sales(
        self,
        rows: list[dict[str, Any]],
        recorded_by: str,
    ) -> dict[str, Any]:
        keys = [(row["sale_date"], row["menu_item_id"]) for row in rows]
        if len(keys) != len(set(keys)):
            raise ValueError("A date and menu item can appear only once in an import")

        menu_ids = sorted({row["menu_item_id"] for row in rows})
        with self.pool.connection() as connection:
            with connection.transaction():
                with connection.cursor(row_factory=dict_row) as cursor:
                    cursor.execute(
                        """
                        SELECT
                            mi.menu_item_id,
                            mi.menu_item_name,
                            COUNT(r.recipe_id) AS recipe_count
                        FROM cafe_stock_manage.menu_items AS mi
                        LEFT JOIN cafe_stock_manage.recipes AS r
                          ON r.menu_item_id = mi.menu_item_id
                        WHERE mi.menu_item_id = ANY(%s) AND mi.is_active
                        GROUP BY mi.menu_item_id
                        """,
                        (menu_ids,),
                    )
                    menus = {row["menu_item_id"]: row for row in cursor.fetchall()}
                    missing = sorted(set(menu_ids) - set(menus))
                    if missing:
                        raise ValueError(f"Unknown active menu items: {', '.join(missing)}")
                    without_recipe = sorted(
                        row["menu_item_name"]
                        for row in menus.values()
                        if row["recipe_count"] == 0
                    )
                    if without_recipe:
                        raise ValueError(
                            "Menu items have no recipe: " + ", ".join(without_recipe)
                        )

                    inserted_sales: list[dict[str, Any]] = []
                    movement_count = 0
                    batch_key = str(uuid4())
                    for index, row in enumerate(rows, start=1):
                        source_key = f"POS-IMPORT-{batch_key}-{index}"
                        cursor.execute(
                            """
                            INSERT INTO cafe_stock_manage.pos_sales (
                                source_key,
                                sale_date,
                                menu_item_id,
                                quantity_sold,
                                unit_price,
                                notes
                            )
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (sale_date, menu_item_id) DO NOTHING
                            RETURNING
                                pos_sale_id,
                                source_key,
                                sale_date,
                                menu_item_id,
                                quantity_sold,
                                unit_price,
                                gross_revenue
                            """,
                            (
                                source_key,
                                row["sale_date"],
                                row["menu_item_id"],
                                row["quantity_sold"],
                                row["unit_price"],
                                "Imported through POS usage workflow",
                            ),
                        )
                        sale = cursor.fetchone()
                        if sale is None:
                            continue
                        inserted_sales.append(sale)
                        cursor.execute(
                            "SELECT movement_id FROM cafe_stock_manage.post_pos_sale_usage(%s, %s)",
                            (sale["pos_sale_id"], recorded_by),
                        )
                        movement_count += len(cursor.fetchall())

        return {
            "received_rows": len(rows),
            "inserted_rows": len(inserted_sales),
            "skipped_rows": len(rows) - len(inserted_sales),
            "movement_count": movement_count,
            "sales": inserted_sales,
        }

    def sales_forecast(self, days: int) -> list[dict[str, Any]]:
        return self.fetch_all(
            """
            SELECT
                forecast_date,
                weekday_name,
                forecast_items_sold,
                forecast_revenue,
                revenue_lower_bound,
                revenue_upper_bound,
                trend_factor,
                forecast_method
            FROM cafe_stock_manage.forecast_daily_sales
            ORDER BY forecast_date
            LIMIT %s
            """,
            (days,),
        )

    def inventory_forecast(self) -> list[dict[str, Any]]:
        return self.fetch_all(
            """
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
                days_of_cover,
                projected_quantity_7_days,
                projected_quantity_14_days,
                expected_stockout_date,
                risk_status
            FROM cafe_stock_manage.inventory_depletion_forecast
            ORDER BY
                CASE risk_status
                    WHEN 'STOCKOUT' THEN 1
                    WHEN 'CRITICAL' THEN 2
                    WHEN 'WATCH' THEN 3
                    WHEN 'HEALTHY' THEN 4
                    ELSE 5
                END,
                days_of_cover NULLS LAST,
                product_name
            """
        )
