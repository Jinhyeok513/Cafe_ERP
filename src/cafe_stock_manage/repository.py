"""Read-only PostgreSQL queries for cafe inventory operations."""

from __future__ import annotations

from datetime import date
from typing import Any

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
