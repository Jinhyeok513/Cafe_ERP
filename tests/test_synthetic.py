from __future__ import annotations

import copy
import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
