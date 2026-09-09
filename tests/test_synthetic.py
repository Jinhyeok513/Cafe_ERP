from __future__ import annotations

import copy
import sys
import unittest
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cafe_stock_manage.synthetic import (  # noqa: E402
    dataset_hash,
    generate_dataset,
    interpolate_revenue,
    load_config,
    menu_weights,
    validate_config,
)


class SyntheticGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config(PROJECT_ROOT / "config" / "prototype_assumptions.json")

    def test_generation_is_reproducible(self) -> None:
        first = generate_dataset(self.config)
        second = generate_dataset(self.config)

        self.assertEqual(first, second)
        self.assertEqual(dataset_hash(first), dataset_hash(second))

    def test_prototype_has_thirty_days_and_close_revenue(self) -> None:
        dataset = generate_dataset(self.config)

        self.assertEqual(len(dataset["calendar"]), 30)
        self.assertEqual(len(dataset["daily_summary"]), 30)
        for row in dataset["daily_summary"]:
            target = Decimal(row["revenue_target"])
            variance = abs(Decimal(row["revenue_variance"]))
            self.assertLess(variance / target, Decimal("0.01"))

    def test_revenue_anchor_grows_from_2024_to_2026(self) -> None:
        anchors = self.config["revenue"]["anchors"]

        early = interpolate_revenue(date(2024, 4, 1), anchors)
        late = interpolate_revenue(date(2026, 12, 31), anchors)

        self.assertEqual(early, Decimal("1650"))
        self.assertEqual(late, Decimal("3750"))
        self.assertGreater(late, early)

    def test_mix_changes_for_season_and_weekend(self) -> None:
        base_row = {
            "day_type": "weekday",
            "season": "summer",
            "weather": "mild",
        }
        summer = menu_weights(self.config, base_row)
        winter = menu_weights(self.config, {**base_row, "season": "winter"})
        weekend = menu_weights(
            self.config,
            {**base_row, "day_type": "weekend", "season": "autumn"},
        )
        weekday = menu_weights(self.config, {**base_row, "season": "autumn"})

        self.assertGreater(summer["DEMO_ICED_LATTE"], winter["DEMO_ICED_LATTE"])
        self.assertGreater(winter["DEMO_FLAT_WHITE"], summer["DEMO_FLAT_WHITE"])
        self.assertGreater(
            weekend["DEMO_EGG_BREAKFAST"],
            weekday["DEMO_EGG_BREAKFAST"],
        )

    def test_oat_latte_usage_is_converted_to_cartons(self) -> None:
        dataset = generate_dataset(self.config)
        oat_rows = [
            row
            for row in dataset["inventory_usage"]
            if row["menu_item_id"] == "DEMO_OAT_LATTE"
            and row["product_id"] == "MILK_OAT"
        ]

        self.assertTrue(oat_rows)
        for row in oat_rows:
            expected = -Decimal(row["quantity_sold"]) * Decimal("0.25")
            self.assertEqual(Decimal(row["quantity_change"]), expected)
            self.assertEqual(row["inventory_unit"], "carton")

    def test_recipe_unit_mismatch_is_rejected(self) -> None:
        invalid = copy.deepcopy(self.config)
        invalid["recipes"][0]["ingredient_unit"] = "millilitre"

        with self.assertRaisesRegex(ValueError, "must be litre"):
            validate_config(invalid)

    def test_clean_operations_follow_delivery_and_balance_rules(self) -> None:
        dataset = generate_dataset(self.config)
        suppliers = {
            item["supplier_id"]: set(item["delivery_weekdays"])
            for item in self.config["suppliers"]
        }

        self.assertTrue(dataset["purchase_orders"])
        self.assertTrue(dataset["goods_receipts"])
        for receipt in dataset["goods_receipts"]:
            receipt_day = date.fromisoformat(receipt["received_datetime"][:10])
            self.assertIn(receipt_day.weekday(), suppliers[receipt["supplier_id"]])

        restricted_sunday_receipts = [
            receipt
            for receipt in dataset["goods_receipts"]
            if receipt["supplier_id"] in {"SUP_A", "SUP_B"}
            and date.fromisoformat(receipt["received_datetime"][:10]).weekday() == 6
        ]
        self.assertEqual(restricted_sunday_receipts, [])

        for item in dataset["stocktake_items"]:
            self.assertGreaterEqual(Decimal(item["system_quantity"]), 0)
            self.assertEqual(item["physical_quantity"], item["system_quantity"])
            self.assertEqual(Decimal(item["variance"]), 0)

    def test_clean_receipts_match_inventory_movements(self) -> None:
        dataset = generate_dataset(self.config)
        products = {item["product_id"]: item for item in self.config["products"]}
        receipt_movements = {
            row["source_id"]: row
            for row in dataset["inventory_movements"]
            if row["source_type"] == "GOODS_RECEIPT"
        }

        for receipt_item in dataset["goods_receipt_items"]:
            self.assertEqual(receipt_item["discrepancy_reason"], "NONE")
            self.assertEqual(Decimal(receipt_item["damaged_quantity"]), 0)
            self.assertFalse(receipt_item["wrong_item_flag"])
            movement = receipt_movements[receipt_item["receipt_item_source_key"]]
            expected = (
                Decimal(receipt_item["accepted_quantity"])
                * Decimal(str(products[receipt_item["product_id"]]["pack_size"]))
            )
            self.assertEqual(Decimal(movement["quantity_change"]), expected)

    def test_error_scenario_is_reproducible(self) -> None:
        first = generate_dataset(self.config, scenario="errors")
        second = generate_dataset(self.config, scenario="errors")

        self.assertEqual(first, second)
        self.assertEqual(dataset_hash(first), dataset_hash(second))

    def test_receipt_errors_post_only_accepted_quantity(self) -> None:
        dataset = generate_dataset(self.config, scenario="errors")
        products = {item["product_id"]: item for item in self.config["products"]}
        receipt_movements = {
            row["source_id"]: row
            for row in dataset["inventory_movements"]
            if row["source_type"] == "GOODS_RECEIPT"
        }
        discrepancies = [
            item
            for item in dataset["goods_receipt_items"]
            if item["discrepancy_reason"] != "NONE"
        ]

        self.assertEqual(
            Counter(item["discrepancy_reason"] for item in discrepancies),
            Counter({"SHORT_DELIVERY": 3, "MISSING_ITEM": 2, "WRONG_PRODUCT": 1}),
        )
        self.assertTrue(all(Decimal(item["damaged_quantity"]) == 0 for item in discrepancies))

        for item in dataset["goods_receipt_items"]:
            accepted = Decimal(item["accepted_quantity"])
            movement = receipt_movements.get(item["receipt_item_source_key"])
            if accepted == 0:
                self.assertIsNone(movement)
                continue
            expected = accepted * Decimal(str(products[item["product_id"]]["pack_size"]))
            self.assertIsNotNone(movement)
            self.assertEqual(Decimal(movement["quantity_change"]), expected)

        discrepancy_receipts = {item["receipt_source_key"] for item in discrepancies}
        discrepancy_po_keys = {
            receipt["po_source_key"]
            for receipt in dataset["goods_receipts"]
            if receipt["receipt_source_key"] in discrepancy_receipts
        }
        order_status = {
            order["po_source_key"]: order["order_status"]
            for order in dataset["purchase_orders"]
        }
        self.assertTrue(
            all(order_status[key] == "PARTIALLY_RECEIVED" for key in discrepancy_po_keys)
        )

    def test_stocktake_variance_creates_new_adjustment(self) -> None:
        dataset = generate_dataset(self.config, scenario="errors")
        variance_items = [
            item for item in dataset["stocktake_items"] if Decimal(item["variance"]) != 0
        ]
        adjustments = {
            row["source_id"]: row
            for row in dataset["inventory_movements"]
            if row["source_type"] == "STOCKTAKE"
        }

        self.assertEqual(len(variance_items), 3)
        self.assertEqual(len(dataset["scenario_events"]), 9)
        for item in variance_items:
            adjustment = adjustments[item["stocktake_item_source_key"]]
            self.assertEqual(adjustment["movement_type"], "ADJUSTMENT")
            self.assertEqual(adjustment["reason_code"], "STOCKTAKE_CORRECTION")
            self.assertEqual(Decimal(adjustment["quantity_change"]), Decimal(item["variance"]))
            self.assertEqual(item["review_status"], "ADJUSTED")
            self.assertGreaterEqual(Decimal(item["physical_quantity"]), 0)

    def test_stocktake_system_quantity_matches_ledger(self) -> None:
        for scenario in ("clean", "errors"):
            dataset = generate_dataset(self.config, scenario=scenario)
            stocktake_datetimes = {
                row["stocktake_source_key"]: row["stocktake_datetime"]
                for row in dataset["stocktakes"]
            }
            movements_by_product: dict[str, list[dict[str, object]]] = {}
            for movement in dataset["inventory_movements"]:
                movements_by_product.setdefault(movement["product_id"], []).append(movement)

            for item in dataset["stocktake_items"]:
                stocktake_datetime = stocktake_datetimes[item["stocktake_source_key"]]
                ledger_quantity = sum(
                    (
                        Decimal(movement["quantity_change"])
                        for movement in movements_by_product[item["product_id"]]
                        if movement["movement_datetime"] < stocktake_datetime
                    ),
                    Decimal(0),
                )
                self.assertEqual(
                    Decimal(item["system_quantity"]),
                    ledger_quantity,
                    f"{scenario}: {item['stocktake_item_source_key']}",
                )

    def test_unknown_scenario_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown generation scenario"):
            generate_dataset(self.config, scenario="surprise")


if __name__ == "__main__":
    unittest.main()
