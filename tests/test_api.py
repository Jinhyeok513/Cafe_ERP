from __future__ import annotations

import sys
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from cafe_stock_manage.api import create_app  # noqa: E402


class FakeInventoryRepository:
    def health(self):
        return {
            "database_connected": True,
            "scenario": "errors",
            "dataset_sha256": "a" * 64,
            "imported_at": datetime(2024, 5, 1, 8, 0),
        }

    def kpis(self):
        return {
            "active_products": 9,
            "reorder_due_products": 2,
            "negative_stock_products": 0,
            "receipt_lines": 93,
            "discrepancy_lines": 6,
            "receiving_accuracy_percent": 93.55,
            "waste_events": 30,
            "movement_count": 552,
            "latest_inventory_accuracy_percent": Decimal("100.00"),
            "data_quality_issue_count": 0,
        }

    def inventory(self, status, search, limit, offset):
        del status, search, limit, offset
        return [
            {
                "product_id": "MILK_OAT",
                "product_name": "Oat Milk",
                "category": "MILK",
                "inventory_unit": "carton",
                "current_quantity": Decimal("3.5"),
                "reorder_point_inventory_qty": Decimal("3"),
                "stock_status": "IN_STOCK",
            }
        ]

    def inventory_product(self, product_id):
        if product_id == "UNKNOWN":
            return None
        return self.inventory(None, None, 1, 0)[0]

    def movements(self, product_id, movement_type, limit):
        del product_id, movement_type, limit
        return [
            {
                "movement_id": 1,
                "movement_source_key": "MOV-1",
                "product_id": "MILK_OAT",
                "product_name": "Oat Milk",
                "inventory_unit": "carton",
                "movement_datetime": datetime(2024, 4, 1, 17, 0),
                "movement_type": "USE",
                "quantity_change": Decimal("-1.5"),
                "running_quantity": Decimal("3.5"),
                "source_type": "POS_SALE",
                "source_id": "POS-1",
                "reason_code": None,
                "recorded_by": "SYSTEM",
            }
        ]

    def discrepancies(self, reason, supplier_id, limit, offset):
        del reason, supplier_id, limit, offset
        return [
            {
                "receipt_source_key": "GR-1",
                "received_datetime": datetime(2024, 4, 4, 8, 0),
                "supplier_id": "SUP_B",
                "receipt_item_source_key": "GRI-1",
                "product_id": "MILK_OAT",
                "product_name": "Oat Milk",
                "order_unit": "carton",
                "invoice_quantity": Decimal("12"),
                "received_quantity": Decimal("10"),
                "damaged_quantity": Decimal("0"),
                "accepted_quantity": Decimal("10"),
                "wrong_item_flag": False,
                "discrepancy_reason": "SHORT_DELIVERY",
            }
        ]

    def stocktake_accuracy(self, date_from, date_to, limit):
        del date_from, date_to, limit
        return [
            {
                "stocktake_id": 1,
                "source_key": "ST-1",
                "stocktake_date": date(2024, 4, 1),
                "products_counted": 9,
                "products_matched": 9,
                "products_with_variance": 0,
                "inventory_accuracy_percent": Decimal("100.00"),
                "absolute_variance_quantity": Decimal("0"),
            }
        ]

    def reorder_recommendations(self, urgency):
        del urgency
        return [
            {
                "product_id": "EGGS",
                "product_name": "Eggs",
                "category": "FOOD",
                "supplier_id": "SUP_C",
                "supplier_name": "Food Supplier",
                "inventory_unit": "each",
                "order_unit": "tray",
                "pack_size": Decimal("25"),
                "current_quantity": Decimal("41"),
                "on_order_quantity": Decimal("0"),
                "average_daily_usage": Decimal("12.5"),
                "lead_time_days": 3,
                "safety_stock_inventory_qty": Decimal("25"),
                "reorder_point_inventory_qty": Decimal("50"),
                "projected_on_delivery": Decimal("3.5"),
                "target_inventory_quantity": Decimal("100"),
                "recommended_order_quantity": Decimal("9"),
                "expected_delivery_date": date(2026, 9, 12),
                "urgency": "ORDER_NOW",
            }
        ]

    def create_draft_purchase_order(
        self, supplier_id, expected_delivery_date, ordered_by, items
    ):
        if supplier_id == "UNKNOWN":
            raise ValueError("Unknown supplier")
        return {
            "po_id": 101,
            "source_key": "DRAFT-test",
            "supplier_id": supplier_id,
            "order_datetime": datetime(2026, 9, 9, 12, 0),
            "expected_delivery_date": expected_delivery_date,
            "order_status": "DRAFT",
            "ordered_by": ordered_by,
            "items": [
                {
                    "po_item_id": 201,
                    "product_id": item["product_id"],
                    "ordered_quantity": item["ordered_quantity"],
                    "order_unit": "tray",
                }
                for item in items
            ],
        }

    def pos_days(self, limit):
        del limit
        return [
            {
                "sale_date": date(2024, 4, 30),
                "menu_lines": 8,
                "items_sold": 208,
                "gross_revenue": Decimal("1735.50"),
                "posted_lines": 8,
                "pending_lines": 0,
                "missing_recipe_lines": 0,
            }
        ]

    def pos_usage(self, sale_date):
        del sale_date
        return [
            {
                "sale_date": date(2024, 4, 30),
                "product_id": "MILK_OAT",
                "product_name": "Oat Milk",
                "category": "MILK",
                "inventory_unit": "carton",
                "usage_quantity": Decimal("9.75"),
                "contributing_menu_items": 1,
            }
        ]

    def menu_items(self):
        return [
            {
                "menu_item_id": "DEMO_OAT_LATTE",
                "menu_item_name": "Demo Oat Latte",
                "menu_category": "HOT_COFFEE",
                "selling_price": Decimal("6.20"),
                "recipe_ingredient_count": 2,
            }
        ]

    def import_pos_sales(self, rows, recorded_by):
        del recorded_by
        if rows[0]["menu_item_id"] == "UNKNOWN":
            raise ValueError("Unknown active menu items: UNKNOWN")
        return {
            "received_rows": len(rows),
            "inserted_rows": len(rows),
            "skipped_rows": 0,
            "movement_count": 2,
            "sales": [
                {
                    "pos_sale_id": 301,
                    "source_key": "POS-IMPORT-test-1",
                    **row,
                    "gross_revenue": row["quantity_sold"] * row["unit_price"],
                }
                for row in rows
            ],
        }


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_context = TestClient(create_app(FakeInventoryRepository()))
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)

    def test_health_and_kpis(self) -> None:
        health = self.client.get("/api/health")
        kpis = self.client.get("/api/kpis")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["scenario"], "errors")
        self.assertEqual(kpis.status_code, 200)
        self.assertEqual(kpis.json()["discrepancy_lines"], 6)

    def test_inventory_and_movements(self) -> None:
        inventory = self.client.get("/api/inventory")
        movements = self.client.get("/api/inventory/MILK_OAT/movements")

        self.assertEqual(inventory.status_code, 200)
        self.assertEqual(inventory.json()[0]["inventory_unit"], "carton")
        self.assertEqual(movements.status_code, 200)
        self.assertEqual(movements.json()[0]["quantity_change"], "-1.5")

    def test_unknown_product_returns_not_found(self) -> None:
        response = self.client.get("/api/inventory/UNKNOWN/movements")

        self.assertEqual(response.status_code, 404)

    def test_discrepancies_and_stocktakes(self) -> None:
        discrepancies = self.client.get("/api/discrepancies")
        stocktakes = self.client.get("/api/stocktakes/accuracy")

        self.assertEqual(discrepancies.status_code, 200)
        self.assertEqual(discrepancies.json()[0]["discrepancy_reason"], "SHORT_DELIVERY")
        self.assertEqual(stocktakes.status_code, 200)
        self.assertEqual(stocktakes.json()[0]["inventory_accuracy_percent"], "100.00")

    def test_invalid_filters_are_rejected(self) -> None:
        invalid_status = self.client.get("/api/inventory?status=UNKNOWN")
        invalid_dates = self.client.get(
            "/api/stocktakes/accuracy?date_from=2024-05-01&date_to=2024-04-01"
        )

        self.assertEqual(invalid_status.status_code, 422)
        self.assertEqual(invalid_dates.status_code, 422)

    def test_reorder_recommendations_and_draft_creation(self) -> None:
        recommendations = self.client.get("/api/reorder/recommendations")
        draft = self.client.post(
            "/api/purchase-orders/drafts",
            json={
                "supplier_id": "SUP_C",
                "expected_delivery_date": "2026-09-12",
                "ordered_by": "Manager",
                "items": [{"product_id": "EGGS", "ordered_quantity": "9"}],
            },
        )

        self.assertEqual(recommendations.status_code, 200)
        self.assertEqual(recommendations.json()[0]["order_unit"], "tray")
        self.assertEqual(draft.status_code, 201)
        self.assertEqual(draft.json()["order_status"], "DRAFT")
        self.assertEqual(draft.json()["items"][0]["ordered_quantity"], "9")

    def test_invalid_draft_is_rejected(self) -> None:
        empty_items = self.client.post(
            "/api/purchase-orders/drafts",
            json={
                "supplier_id": "SUP_C",
                "expected_delivery_date": "2026-09-12",
                "ordered_by": "Manager",
                "items": [],
            },
        )
        invalid_supplier = self.client.post(
            "/api/purchase-orders/drafts",
            json={
                "supplier_id": "UNKNOWN",
                "expected_delivery_date": "2026-09-12",
                "ordered_by": "Manager",
                "items": [{"product_id": "EGGS", "ordered_quantity": "9"}],
            },
        )

        self.assertEqual(empty_items.status_code, 422)
        self.assertEqual(invalid_supplier.status_code, 422)

    def test_pos_usage_reporting_and_import(self) -> None:
        days = self.client.get("/api/pos/days")
        usage = self.client.get("/api/pos/usage")
        menu_items = self.client.get("/api/pos/menu-items")
        imported = self.client.post(
            "/api/pos/import",
            json={
                "recorded_by": "Manager",
                "rows": [
                    {
                        "sale_date": "2026-09-09",
                        "menu_item_id": "DEMO_OAT_LATTE",
                        "quantity_sold": 4,
                        "unit_price": "6.20",
                    }
                ],
            },
        )

        self.assertEqual(days.status_code, 200)
        self.assertEqual(days.json()[0]["posted_lines"], 8)
        self.assertEqual(usage.json()[0]["inventory_unit"], "carton")
        self.assertEqual(menu_items.json()[0]["recipe_ingredient_count"], 2)
        self.assertEqual(imported.status_code, 201)
        self.assertEqual(imported.json()["movement_count"], 2)

    def test_invalid_pos_import_is_rejected(self) -> None:
        invalid_quantity = self.client.post(
            "/api/pos/import",
            json={
                "recorded_by": "Manager",
                "rows": [
                    {
                        "sale_date": "2026-09-09",
                        "menu_item_id": "DEMO_OAT_LATTE",
                        "quantity_sold": 0,
                        "unit_price": "6.20",
                    }
                ],
            },
        )
        unknown_menu = self.client.post(
            "/api/pos/import",
            json={
                "recorded_by": "Manager",
                "rows": [
                    {
                        "sale_date": "2026-09-09",
                        "menu_item_id": "UNKNOWN",
                        "quantity_sold": 1,
                        "unit_price": "6.20",
                    }
                ],
            },
        )

        self.assertEqual(invalid_quantity.status_code, 422)
        self.assertEqual(unknown_menu.status_code, 422)


if __name__ == "__main__":
    unittest.main()
