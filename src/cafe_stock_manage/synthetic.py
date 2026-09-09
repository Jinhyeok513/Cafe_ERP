"""Deterministic synthetic sales and ingredient usage generation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any


MONEY = Decimal("0.01")
QUANTITY = Decimal("0.000001")


def decimal_value(value: Any) -> Decimal:
    return Decimal(str(value))


def format_decimal(value: Decimal, places: Decimal = QUANTITY) -> str:
    normalized = value.quantize(places, rounding=ROUND_HALF_UP)
    return format(normalized, "f")


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def load_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as config_file:
        config = json.load(config_file)
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    metadata = config.get("metadata", {})
    if metadata.get("assumption_status") != "synthetic_demo":
        raise ValueError("Synthetic config must declare assumption_status=synthetic_demo")

    date_range = config.get("date_range", {})
    if int(date_range.get("days", 0)) <= 0:
        raise ValueError("date_range.days must be positive")
    parse_date(date_range["start_date"])

    anchors = config.get("revenue", {}).get("anchors", [])
    if len(anchors) < 2:
        raise ValueError("At least two revenue anchors are required")
    anchor_dates = [parse_date(anchor["date"]) for anchor in anchors]
    if anchor_dates != sorted(anchor_dates):
        raise ValueError("Revenue anchors must be ordered by date")

    products = {item["product_id"]: item for item in config.get("products", [])}
    suppliers = {item["supplier_id"]: item for item in config.get("suppliers", [])}
    menu_items = {item["menu_item_id"]: item for item in config.get("menu_items", [])}
    if len(products) != len(config.get("products", [])):
        raise ValueError("Duplicate product_id in synthetic config")
    if len(menu_items) != len(config.get("menu_items", [])):
        raise ValueError("Duplicate menu_item_id in synthetic config")
    if len(suppliers) != len(config.get("suppliers", [])):
        raise ValueError("Duplicate supplier_id in synthetic config")

    required_product_fields = (
        "supplier_id",
        "order_unit",
        "pack_size",
        "opening_inventory_qty",
        "typical_order_qty",
        "reorder_point_inventory_qty",
        "safety_stock_inventory_qty",
    )
    for product_id, product in products.items():
        if product.get("supplier_id") not in suppliers:
            raise ValueError(f"Unknown supplier for product {product_id}")
        missing_fields = [field for field in required_product_fields if field not in product]
        if missing_fields:
            raise ValueError(f"Missing operational fields for {product_id}: {', '.join(missing_fields)}")
        if decimal_value(product["pack_size"]) <= 0:
            raise ValueError(f"pack_size must be positive for {product_id}")

    for supplier_id, supplier in suppliers.items():
        weekdays = supplier.get("delivery_weekdays", [])
        if not weekdays or any(day < 0 or day > 6 for day in weekdays):
            raise ValueError(f"Invalid delivery weekdays for {supplier_id}")

    recipe_pairs: set[tuple[str, str]] = set()
    menus_with_recipes: set[str] = set()
    for recipe in config.get("recipes", []):
        menu_id = recipe["menu_item_id"]
        product_id = recipe["product_id"]
        if menu_id not in menu_items:
            raise ValueError(f"Unknown recipe menu item: {menu_id}")
        if product_id not in products:
            raise ValueError(f"Unknown recipe product: {product_id}")
        pair = (menu_id, product_id)
        if pair in recipe_pairs:
            raise ValueError(f"Duplicate recipe ingredient: {menu_id}/{product_id}")
        recipe_pairs.add(pair)
        menus_with_recipes.add(menu_id)

        product = products[product_id]
        expected_unit = product.get("content_unit") or product["inventory_unit"]
        if recipe["ingredient_unit"] != expected_unit:
            raise ValueError(
                f"Recipe unit for {menu_id}/{product_id} must be {expected_unit}"
            )
        if decimal_value(recipe["ingredient_quantity"]) <= 0:
            raise ValueError("Recipe ingredient quantities must be positive")

    missing_recipes = sorted(set(menu_items) - menus_with_recipes)
    if missing_recipes:
        raise ValueError(f"Menu items without recipes: {', '.join(missing_recipes)}")

    for season, probabilities in config.get("weather", {}).get("probabilities", {}).items():
        if not probabilities or sum(decimal_value(v) for v in probabilities.values()) <= 0:
            raise ValueError(f"Weather probabilities are invalid for {season}")

    error_config = config.get("error_injection", {})
    receipt_rule_keys: set[tuple[str, int]] = set()
    supported_receipt_reasons = {"SHORT_DELIVERY", "MISSING_ITEM", "WRONG_PRODUCT"}
    for rule in error_config.get("receipt_discrepancies", []):
        product_id = rule.get("product_id")
        occurrence = int(rule.get("occurrence", 0))
        reason = rule.get("reason")
        if product_id not in products:
            raise ValueError(f"Unknown receipt discrepancy product: {product_id}")
        if occurrence <= 0:
            raise ValueError("Receipt discrepancy occurrence must be positive")
        if reason not in supported_receipt_reasons:
            raise ValueError(f"Unsupported receipt discrepancy reason: {reason}")
        rule_key = (product_id, occurrence)
        if rule_key in receipt_rule_keys:
            raise ValueError(f"Duplicate receipt discrepancy rule: {rule_key}")
        receipt_rule_keys.add(rule_key)
        if reason == "SHORT_DELIVERY":
            if decimal_value(rule.get("short_by_order_units", 0)) <= 0:
                raise ValueError("SHORT_DELIVERY requires positive short_by_order_units")
        elif "short_by_order_units" in rule:
            raise ValueError(f"{reason} must not set short_by_order_units")

    stocktake_rule_keys: set[tuple[str, str]] = set()
    start_date = parse_date(date_range["start_date"])
    end_date = start_date + timedelta(days=int(date_range["days"]) - 1)
    for rule in error_config.get("stocktake_variances", []):
        product_id = rule.get("product_id")
        rule_date = parse_date(rule["date"])
        if product_id not in products:
            raise ValueError(f"Unknown stocktake variance product: {product_id}")
        if not start_date <= rule_date <= end_date:
            raise ValueError(f"Stocktake variance date is outside generation range: {rule_date}")
        if decimal_value(rule.get("variance_inventory_qty", 0)) == 0:
            raise ValueError("Stocktake variance must be non-zero")
        rule_key = (rule["date"], product_id)
        if rule_key in stocktake_rule_keys:
            raise ValueError(f"Duplicate stocktake variance rule: {rule_key}")
        stocktake_rule_keys.add(rule_key)


def season_for_day(day: date) -> str:
    if day.month in (12, 1, 2):
        return "summer"
    if day.month in (3, 4, 5):
        return "autumn"
    if day.month in (6, 7, 8):
        return "winter"
    return "spring"


def interpolate_revenue(day: date, anchors: list[dict[str, Any]]) -> Decimal:
    points = [(parse_date(item["date"]), decimal_value(item["daily_revenue"])) for item in anchors]
    if day <= points[0][0]:
        return points[0][1]
    if day >= points[-1][0]:
        return points[-1][1]

    for (left_date, left_value), (right_date, right_value) in zip(points, points[1:]):
        if left_date <= day <= right_date:
            elapsed = Decimal((day - left_date).days)
            total = Decimal((right_date - left_date).days)
            return left_value + (right_value - left_value) * elapsed / total

    raise RuntimeError("Revenue anchor interpolation failed")


def date_in_periods(day: date, periods: list[dict[str, str]]) -> bool:
    return any(
        parse_date(period["start_date"]) <= day <= parse_date(period["end_date"])
        for period in periods
    )


def choose_weather(
    rng: random.Random,
    season: str,
    probabilities: dict[str, dict[str, float]],
) -> str:
    options = list(probabilities[season])
    weights = [probabilities[season][option] for option in options]
    return rng.choices(options, weights=weights, k=1)[0]


def category_multiplier(
    multiplier_group: dict[str, dict[str, float]],
    key: str,
    category: str,
) -> Decimal:
    return decimal_value(multiplier_group.get(key, {}).get(category, 1))


def menu_weights(config: dict[str, Any], calendar_row: dict[str, Any]) -> dict[str, Decimal]:
    mix = config["mix"]
    weights: dict[str, Decimal] = {}
    for menu_item in config["menu_items"]:
        category = menu_item["category"]
        weight = decimal_value(menu_item["base_mix_weight"])
        weight *= category_multiplier(
            mix["day_type_category_multipliers"],
            calendar_row["day_type"],
            category,
        )
        weight *= category_multiplier(
            mix["season_category_multipliers"],
            calendar_row["season"],
            category,
        )
        weight *= category_multiplier(
            mix["weather_category_multipliers"],
            calendar_row["weather"],
            category,
        )
        weights[menu_item["menu_item_id"]] = weight
    return weights


def build_calendar(config: dict[str, Any], rng: random.Random) -> list[dict[str, Any]]:
    start_date = parse_date(config["date_range"]["start_date"])
    days = int(config["date_range"]["days"])
    weather_config = config["weather"]
    university_breaks = config["calendar"].get("university_breaks", [])
    public_holidays = {parse_date(value) for value in config["calendar"].get("public_holidays", [])}
    rows: list[dict[str, Any]] = []

    for offset in range(days):
        day = start_date + timedelta(days=offset)
        season = season_for_day(day)
        rows.append(
            {
                "date": day.isoformat(),
                "weekday": day.strftime("%A"),
                "day_type": "weekend" if day.weekday() >= 5 else "weekday",
                "season": season,
                "weather": choose_weather(rng, season, weather_config["probabilities"]),
                "is_public_holiday": day in public_holidays,
                "is_university_break": date_in_periods(day, university_breaks),
            }
        )
    return rows


def build_revenue_target(
    config: dict[str, Any],
    calendar_row: dict[str, Any],
    rng: random.Random,
) -> Decimal:
    revenue = config["revenue"]
    day = parse_date(calendar_row["date"])
    baseline = interpolate_revenue(day, revenue["anchors"])
    factor = decimal_value(revenue["day_type_multipliers"][calendar_row["day_type"]])
    factor *= decimal_value(revenue["weather_multipliers"][calendar_row["weather"]])
    if calendar_row["is_university_break"]:
        factor *= decimal_value(revenue["university_break_multiplier"])
    if calendar_row["is_public_holiday"]:
        factor *= decimal_value(revenue["public_holiday_multiplier"])

    noise = 1 + rng.gauss(0, float(revenue["daily_noise_standard_deviation"]))
    noise = max(float(revenue["minimum_noise_multiplier"]), noise)
    noise = min(float(revenue["maximum_noise_multiplier"]), noise)
    return (baseline * factor * decimal_value(noise)).quantize(MONEY, rounding=ROUND_HALF_UP)


def allocate_menu_sales(
    config: dict[str, Any],
    calendar_row: dict[str, Any],
    revenue_target: Decimal,
) -> list[dict[str, Any]]:
    weights = menu_weights(config, calendar_row)
    total_weight = sum(weights.values(), Decimal(0))
    quantities: dict[str, int] = {}
    items = {item["menu_item_id"]: item for item in config["menu_items"]}

    for menu_id, weight in weights.items():
        price = decimal_value(items[menu_id]["selling_price"])
        desired_revenue = revenue_target * weight / total_weight
        quantities[menu_id] = max(
            0,
            int((desired_revenue / price).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        )

    def achieved_revenue() -> Decimal:
        return sum(
            decimal_value(items[menu_id]["selling_price"]) * quantity
            for menu_id, quantity in quantities.items()
        )

    for _ in range(100):
        current = achieved_revenue()
        residual = revenue_target - current
        current_error = abs(residual)
        best_action: tuple[str, int] | None = None
        best_error = current_error
        for menu_id, item in items.items():
            price = decimal_value(item["selling_price"])
            if residual > 0:
                candidate_error = abs(residual - price)
                action = 1
            elif quantities[menu_id] > 0:
                candidate_error = abs(residual + price)
                action = -1
            else:
                continue
            if candidate_error < best_error:
                best_error = candidate_error
                best_action = (menu_id, action)
        if best_action is None:
            break
        quantities[best_action[0]] += best_action[1]

    rows: list[dict[str, Any]] = []
    for menu_id in sorted(quantities):
        quantity = quantities[menu_id]
        if quantity == 0:
            continue
        price = decimal_value(items[menu_id]["selling_price"])
        rows.append(
            {
                "pos_source_key": f"POS-{calendar_row['date'].replace('-', '')}-{menu_id}",
                "sale_date": calendar_row["date"],
                "menu_item_id": menu_id,
                "quantity_sold": quantity,
                "unit_price": format_decimal(price, MONEY),
                "gross_revenue": format_decimal(price * quantity, MONEY),
            }
        )
    return rows


def derive_inventory_usage(
    config: dict[str, Any],
    pos_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    products = {item["product_id"]: item for item in config["products"]}
    recipes_by_menu: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for recipe in config["recipes"]:
        recipes_by_menu[recipe["menu_item_id"]].append(recipe)

    usage_rows: list[dict[str, Any]] = []
    for sale in pos_rows:
        for recipe in recipes_by_menu[sale["menu_item_id"]]:
            product = products[recipe["product_id"]]
            ingredient_quantity = decimal_value(recipe["ingredient_quantity"])
            content_quantity = product.get("content_quantity_per_inventory_unit")
            inventory_quantity_per_item = ingredient_quantity
            if content_quantity is not None:
                inventory_quantity_per_item /= decimal_value(content_quantity)
            quantity_change = -inventory_quantity_per_item * int(sale["quantity_sold"])
            usage_rows.append(
                {
                    "sale_date": sale["sale_date"],
                    "pos_source_key": sale["pos_source_key"],
                    "menu_item_id": sale["menu_item_id"],
                    "product_id": recipe["product_id"],
                    "quantity_sold": sale["quantity_sold"],
                    "recipe_quantity": format_decimal(ingredient_quantity),
                    "recipe_unit": recipe["ingredient_unit"],
                    "inventory_unit": product["inventory_unit"],
                    "quantity_change": format_decimal(quantity_change),
                }
            )
    return usage_rows


def generate_dataset(
    config: dict[str, Any],
    scenario: str = "clean",
) -> dict[str, list[dict[str, Any]]]:
    validate_config(config)
    if scenario not in {"clean", "errors"}:
        raise ValueError(f"Unknown generation scenario: {scenario}")
    rng = random.Random(int(config["metadata"]["random_seed"]))
    calendar_rows = build_calendar(config, rng)
    pos_rows: list[dict[str, Any]] = []
    daily_summary_rows: list[dict[str, Any]] = []

    for calendar_row in calendar_rows:
        target = build_revenue_target(config, calendar_row, rng)
        daily_pos_rows = allocate_menu_sales(config, calendar_row, target)
        actual = sum(decimal_value(row["gross_revenue"]) for row in daily_pos_rows)
        pos_rows.extend(daily_pos_rows)
        daily_summary_rows.append(
            {
                "date": calendar_row["date"],
                "revenue_target": format_decimal(target, MONEY),
                "actual_revenue": format_decimal(actual, MONEY),
                "revenue_variance": format_decimal(actual - target, MONEY),
            }
        )

    usage_rows = derive_inventory_usage(config, pos_rows)
    menu_rows = [
        {
            "menu_item_id": item["menu_item_id"],
            "menu_item_name": item["menu_item_name"],
            "menu_category": item["category"],
            "selling_price": format_decimal(decimal_value(item["selling_price"]), MONEY),
            "assumption_status": "synthetic_demo",
        }
        for item in config["menu_items"]
    ]
    recipe_rows = [
        {
            **recipe,
            "ingredient_quantity": format_decimal(decimal_value(recipe["ingredient_quantity"])),
            "assumption_status": "synthetic_demo",
        }
        for recipe in config["recipes"]
    ]
    dataset = {
        "calendar": calendar_rows,
        "daily_summary": daily_summary_rows,
        "menu_items": menu_rows,
        "recipes": recipe_rows,
        "pos_sales": pos_rows,
        "inventory_usage": usage_rows,
    }
    from .operations import simulate_operations

    dataset.update(
        simulate_operations(
            config,
            calendar_rows,
            pos_rows,
            usage_rows,
            rng,
            scenario=scenario,
        )
    )
    return dataset


def dataset_hash(dataset: dict[str, list[dict[str, Any]]]) -> str:
    payload = json.dumps(dataset, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_dataset(
    dataset: dict[str, list[dict[str, Any]]],
    config: dict[str, Any],
    output_dir: str | Path,
    scenario: str = "clean",
) -> None:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    for dataset_name, rows in dataset.items():
        csv_path = output_path / f"{dataset_name}.csv"
        if not rows:
            csv_path.write_text("", encoding="utf-8")
            continue
        with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=list(rows[0]),
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)

    manifest = {
        "project": "Cafe_Stock_manage",
        "assumption_status": config["metadata"]["assumption_status"],
        "random_seed": config["metadata"]["random_seed"],
        "scenario": scenario,
        "start_date": config["date_range"]["start_date"],
        "days": config["date_range"]["days"],
        "dataset_sha256": dataset_hash(dataset),
        "row_counts": {name: len(rows) for name, rows in dataset.items()},
    }
    with (output_path / "manifest.json").open("w", encoding="utf-8") as manifest_file:
        json.dump(manifest, manifest_file, indent=2, sort_keys=True)
        manifest_file.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Path to synthetic assumption JSON")
    parser.add_argument("--output", required=True, help="Directory for generated CSV files")
    parser.add_argument(
        "--scenario",
        choices=("clean", "errors"),
        default="clean",
        help="Generate the clean baseline or configured operational errors",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    dataset = generate_dataset(config, scenario=args.scenario)
    write_dataset(dataset, config, args.output, scenario=args.scenario)
    print(
        f"Generated {args.scenario} scenario with {len(dataset['calendar'])} days, "
        f"{len(dataset['pos_sales'])} POS rows and "
        f"{len(dataset['inventory_usage'])} usage rows, "
        f"{len(dataset['purchase_orders'])} orders and "
        f"{len(dataset['goods_receipts'])} receipts."
    )


if __name__ == "__main__":
    main()
