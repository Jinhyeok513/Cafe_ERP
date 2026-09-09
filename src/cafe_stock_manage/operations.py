"""Generate purchase, receipt, movement and stocktake history."""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo


QUANTITY = Decimal("0.000001")


def decimal_value(value: Any) -> Decimal:
    return Decimal(str(value))


def format_quantity(value: Decimal) -> str:
    return format(value.quantize(QUANTITY, rounding=ROUND_HALF_UP), "f")


def local_timestamp(day: date, clock: str, timezone_name: str) -> str:
    local_time = time.fromisoformat(clock)
    value = datetime.combine(day, local_time, tzinfo=ZoneInfo(timezone_name))
    return value.isoformat()


def next_delivery_date(earliest: date, delivery_weekdays: set[int]) -> date:
    candidate = earliest
    for _ in range(14):
        if candidate.weekday() in delivery_weekdays:
            return candidate
        candidate += timedelta(days=1)
    raise ValueError("No supplier delivery day found within two weeks")


def aggregate_daily_usage(
    usage_rows: list[dict[str, Any]],
) -> dict[tuple[date, str], Decimal]:
    totals: dict[tuple[date, str], Decimal] = defaultdict(Decimal)
    for row in usage_rows:
        key = (date.fromisoformat(row["sale_date"]), row["product_id"])
        totals[key] += -decimal_value(row["quantity_change"])
    return totals


def expected_usage_between(
    product_id: str,
    start: date,
    end_exclusive: date,
    daily_usage: dict[tuple[date, str], Decimal],
    average_daily_usage: dict[str, Decimal],
) -> Decimal:
    total = Decimal(0)
    current = start
    while current < end_exclusive:
        total += daily_usage.get((current, product_id), average_daily_usage[product_id])
        current += timedelta(days=1)
    return total


def simulate_operations(
    config: dict[str, Any],
    calendar_rows: list[dict[str, Any]],
    pos_rows: list[dict[str, Any]],
    usage_rows: list[dict[str, Any]],
    rng: random.Random,
    scenario: str = "clean",
) -> dict[str, list[dict[str, Any]]]:
    del pos_rows

    if scenario not in {"clean", "errors"}:
        raise ValueError(f"Unknown generation scenario: {scenario}")

    timezone_name = config["metadata"]["timezone"]
    products = {item["product_id"]: item for item in config["products"]}
    suppliers = {item["supplier_id"]: item for item in config["suppliers"]}
    days = [date.fromisoformat(row["date"]) for row in calendar_rows]
    end_date = days[-1]
    daily_usage = aggregate_daily_usage(usage_rows)
    average_daily_usage = {
        product_id: (
            sum(
                (daily_usage.get((day, product_id), Decimal(0)) for day in days),
                Decimal(0),
            )
            / Decimal(len(days))
        )
        for product_id in products
    }

    balances = {
        product_id: decimal_value(product["opening_inventory_qty"])
        for product_id, product in products.items()
    }
    pending_receipts: dict[date, list[dict[str, Any]]] = defaultdict(list)

    purchase_orders: list[dict[str, Any]] = []
    purchase_order_items: list[dict[str, Any]] = []
    goods_receipts: list[dict[str, Any]] = []
    goods_receipt_items: list[dict[str, Any]] = []
    movements: list[dict[str, Any]] = []
    stocktakes: list[dict[str, Any]] = []
    stocktake_items: list[dict[str, Any]] = []
    scenario_events: list[dict[str, Any]] = []

    error_config = config.get("error_injection", {}) if scenario == "errors" else {}
    receipt_rules = {
        (rule["product_id"], int(rule["occurrence"])): rule
        for rule in error_config.get("receipt_discrepancies", [])
    }
    stocktake_rules = {
        (rule["date"], rule["product_id"]): rule
        for rule in error_config.get("stocktake_variances", [])
    }
    receipt_occurrences: dict[str, int] = defaultdict(int)
    applied_receipt_rules: set[tuple[str, int]] = set()
    applied_stocktake_rules: set[tuple[str, str]] = set()

    start_date = days[0]
    for product_id, product in products.items():
        opening_quantity = decimal_value(product["opening_inventory_qty"])
        if opening_quantity == 0:
            continue
        source_id = f"OPENING-{start_date.isoformat()}-{product_id}"
        movements.append(
            {
                "movement_source_key": source_id,
                "product_id": product_id,
                "movement_datetime": local_timestamp(start_date, "05:00:00", timezone_name),
                "movement_type": "ADJUSTMENT",
                "quantity_change": format_quantity(opening_quantity),
                "source_type": "OPENING_BALANCE",
                "source_id": source_id,
                "reason_code": "OPENING_BALANCE",
                "recorded_by": "Manager",
            }
        )

    for day in days:
        for pending in pending_receipts.pop(day, []):
            po = pending["purchase_order"]
            receipt_source_key = f"GR-{po['po_source_key']}"
            goods_receipts.append(
                {
                    "receipt_source_key": receipt_source_key,
                    "po_source_key": po["po_source_key"],
                    "supplier_id": po["supplier_id"],
                    "received_datetime": local_timestamp(day, "08:00:00", timezone_name),
                    "invoice_number": f"DEMO-{receipt_source_key}",
                    "received_by": "Manager",
                    "receipt_status": "POSTED",
                }
            )
            receipt_has_discrepancy = False
            for item in pending["items"]:
                product = products[item["product_id"]]
                order_quantity = decimal_value(item["ordered_quantity"])
                receipt_occurrences[item["product_id"]] += 1
                rule_key = (item["product_id"], receipt_occurrences[item["product_id"]])
                rule = receipt_rules.get(rule_key)

                received_quantity = order_quantity
                accepted_quantity = order_quantity
                wrong_item_flag = False
                discrepancy_reason = "NONE"
                if rule is not None:
                    discrepancy_reason = rule["reason"]
                    if discrepancy_reason == "SHORT_DELIVERY":
                        received_quantity -= decimal_value(rule["short_by_order_units"])
                        accepted_quantity = received_quantity
                    elif discrepancy_reason == "MISSING_ITEM":
                        received_quantity = Decimal(0)
                        accepted_quantity = Decimal(0)
                    elif discrepancy_reason == "WRONG_PRODUCT":
                        accepted_quantity = Decimal(0)
                        wrong_item_flag = True
                    else:
                        raise ValueError(
                            f"Unsupported receipt discrepancy: {discrepancy_reason}"
                        )
                    if received_quantity < 0:
                        raise ValueError(f"Receipt rule exceeds order quantity: {rule_key}")
                    receipt_has_discrepancy = True
                    applied_receipt_rules.add(rule_key)

                accepted_inventory_quantity = (
                    accepted_quantity * decimal_value(product["pack_size"])
                )
                receipt_item_source_key = f"GRI-{item['po_item_source_key']}"
                goods_receipt_items.append(
                    {
                        "receipt_item_source_key": receipt_item_source_key,
                        "receipt_source_key": receipt_source_key,
                        "po_item_source_key": item["po_item_source_key"],
                        "product_id": item["product_id"],
                        "invoice_quantity": item["ordered_quantity"],
                        "received_quantity": format_quantity(received_quantity),
                        "damaged_quantity": format_quantity(Decimal(0)),
                        "accepted_quantity": format_quantity(accepted_quantity),
                        "wrong_item_flag": wrong_item_flag,
                        "discrepancy_reason": discrepancy_reason,
                    }
                )
                if rule is not None:
                    scenario_events.append(
                        {
                            "event_source_key": receipt_item_source_key,
                            "event_date": day.isoformat(),
                            "event_type": discrepancy_reason,
                            "product_id": item["product_id"],
                            "expected_quantity": format_quantity(order_quantity),
                            "actual_quantity": format_quantity(accepted_quantity),
                            "quantity_unit": product["order_unit"],
                            "resolution": (
                                "ACCEPTED_QUANTITY_POSTED"
                                if accepted_quantity > 0
                                else "NO_RECEIVE_POSTED"
                            ),
                        }
                    )
                if accepted_inventory_quantity > 0:
                    balances[item["product_id"]] += accepted_inventory_quantity
                    movements.append(
                        {
                            "movement_source_key": f"MOV-{receipt_item_source_key}",
                            "product_id": item["product_id"],
                            "movement_datetime": local_timestamp(day, "08:00:00", timezone_name),
                            "movement_type": "RECEIVE",
                            "quantity_change": format_quantity(accepted_inventory_quantity),
                            "source_type": "GOODS_RECEIPT",
                            "source_id": receipt_item_source_key,
                            "reason_code": (
                                discrepancy_reason if discrepancy_reason != "NONE" else ""
                            ),
                            "recorded_by": "Manager",
                        }
                    )
            po["order_status"] = (
                "PARTIALLY_RECEIVED" if receipt_has_discrepancy else "RECEIVED"
            )

        usage_for_day = [row for row in usage_rows if row["sale_date"] == day.isoformat()]
        for usage in usage_for_day:
            quantity_change = decimal_value(usage["quantity_change"])
            balances[usage["product_id"]] += quantity_change
            movements.append(
                {
                    "movement_source_key": f"MOV-{usage['pos_source_key']}-{usage['product_id']}",
                    "product_id": usage["product_id"],
                    "movement_datetime": local_timestamp(day, "17:00:00", timezone_name),
                    "movement_type": "USE",
                    "quantity_change": format_quantity(quantity_change),
                    "source_type": "POS_SALE",
                    "source_id": usage["pos_source_key"],
                    "reason_code": "",
                    "recorded_by": "SYSTEM",
                }
            )

        for product_id, product in products.items():
            usage_quantity = daily_usage.get((day, product_id), Decimal(0))
            waste_rate = decimal_value(product.get("waste_rate_of_usage", 0))
            if usage_quantity == 0 or waste_rate == 0:
                continue
            waste_quantity = usage_quantity * waste_rate * decimal_value(rng.uniform(0.5, 1.5))
            if product["inventory_unit"] == "each":
                waste_quantity = waste_quantity.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            else:
                waste_quantity = waste_quantity.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
            waste_quantity = min(waste_quantity, max(balances[product_id], Decimal(0)))
            if waste_quantity <= 0:
                continue
            balances[product_id] -= waste_quantity
            waste_source_id = f"WASTE-{day.isoformat()}-{product_id}"
            movements.append(
                {
                    "movement_source_key": f"MOV-{waste_source_id}",
                    "product_id": product_id,
                    "movement_datetime": local_timestamp(day, "17:30:00", timezone_name),
                    "movement_type": "WASTE",
                    "quantity_change": format_quantity(-waste_quantity),
                    "source_type": "WASTE_LOG",
                    "source_id": waste_source_id,
                    "reason_code": "SYNTHETIC_NORMAL_WASTE",
                    "recorded_by": "Manager",
                }
            )

        stocktake_source_key = f"ST-{day.isoformat()}"
        stocktakes.append(
            {
                "stocktake_source_key": stocktake_source_key,
                "stocktake_datetime": local_timestamp(day, "18:00:00", timezone_name),
                "stocktake_status": "RECONCILED",
                "performed_by": "Manager",
            }
        )
        for product_id, product in products.items():
            current_quantity = balances[product_id]
            stocktake_rule_key = (day.isoformat(), product_id)
            stocktake_rule = stocktake_rules.get(stocktake_rule_key)
            variance = Decimal(0)
            if stocktake_rule is not None:
                variance = decimal_value(stocktake_rule["variance_inventory_qty"])
            physical_quantity = current_quantity + variance
            if physical_quantity < 0:
                raise ValueError(
                    f"Stocktake variance creates negative physical stock: {stocktake_rule_key}"
                )
            stocktake_item_source_key = f"STI-{day.isoformat()}-{product_id}"
            stocktake_items.append(
                {
                    "stocktake_item_source_key": stocktake_item_source_key,
                    "stocktake_source_key": stocktake_source_key,
                    "product_id": product_id,
                    "inventory_unit": product["inventory_unit"],
                    "physical_quantity": format_quantity(physical_quantity),
                    "system_quantity": format_quantity(current_quantity),
                    "variance": format_quantity(variance),
                    "review_status": "ADJUSTED" if variance != 0 else "MATCH",
                }
            )
            if variance != 0:
                movements.append(
                    {
                        "movement_source_key": f"MOV-{stocktake_item_source_key}",
                        "product_id": product_id,
                        "movement_datetime": local_timestamp(day, "18:00:00", timezone_name),
                        "movement_type": "ADJUSTMENT",
                        "quantity_change": format_quantity(variance),
                        "source_type": "STOCKTAKE",
                        "source_id": stocktake_item_source_key,
                        "reason_code": "STOCKTAKE_CORRECTION",
                        "recorded_by": "Manager",
                    }
                )
                balances[product_id] = physical_quantity
                applied_stocktake_rules.add(stocktake_rule_key)
                scenario_events.append(
                    {
                        "event_source_key": stocktake_item_source_key,
                        "event_date": day.isoformat(),
                        "event_type": "STOCKTAKE_VARIANCE",
                        "product_id": product_id,
                        "expected_quantity": format_quantity(current_quantity),
                        "actual_quantity": format_quantity(physical_quantity),
                        "quantity_unit": product["inventory_unit"],
                        "resolution": "ADJUSTMENT_POSTED",
                    }
                )

        orders_by_supplier: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for product_id, product in products.items():
            supplier = suppliers[product["supplier_id"]]
            delivery_weekdays = set(supplier["delivery_weekdays"])
            earliest = day + timedelta(days=int(supplier["lead_time_days"]))
            delivery_day = next_delivery_date(earliest, delivery_weekdays)
            following_delivery = next_delivery_date(delivery_day + timedelta(days=1), delivery_weekdays)

            pending_before_delivery = sum(
                (
                    decimal_value(item["inventory_quantity"])
                    for receipt_day, pending_list in pending_receipts.items()
                    if receipt_day <= delivery_day
                    for receipt in pending_list
                    for item in receipt["items"]
                    if item["product_id"] == product_id
                ),
                Decimal(0),
            )
            usage_before_delivery = expected_usage_between(
                product_id,
                day + timedelta(days=1),
                delivery_day,
                daily_usage,
                average_daily_usage,
            )
            coverage_demand = expected_usage_between(
                product_id,
                delivery_day,
                following_delivery,
                daily_usage,
                average_daily_usage,
            )
            projected_at_delivery = balances[product_id] + pending_before_delivery - usage_before_delivery
            safety_stock = decimal_value(product["safety_stock_inventory_qty"])
            reorder_point = decimal_value(product["reorder_point_inventory_qty"])
            required_inventory = coverage_demand + safety_stock - projected_at_delivery

            if projected_at_delivery > reorder_point and required_inventory <= 0:
                continue

            pack_size = decimal_value(product["pack_size"])
            required_order_units = max(
                Decimal(0),
                (required_inventory / pack_size).to_integral_value(rounding=ROUND_CEILING),
            )
            minimum_order_units = decimal_value(product["typical_order_qty"])
            order_units = max(required_order_units, minimum_order_units)
            if order_units <= 0:
                continue
            orders_by_supplier[product["supplier_id"]].append(
                {
                    "product_id": product_id,
                    "ordered_quantity": format_quantity(order_units),
                    "order_unit": product["order_unit"],
                    "inventory_quantity": format_quantity(order_units * pack_size),
                    "delivery_date": delivery_day,
                }
            )

        for supplier_id, order_items in sorted(orders_by_supplier.items()):
            delivery_groups: dict[date, list[dict[str, Any]]] = defaultdict(list)
            for item in order_items:
                delivery_groups[item["delivery_date"]].append(item)
            for delivery_day, delivery_items in sorted(delivery_groups.items()):
                po_source_key = f"PO-{day.isoformat()}-{delivery_day.isoformat()}-{supplier_id}"
                purchase_order = {
                    "po_source_key": po_source_key,
                    "supplier_id": supplier_id,
                    "order_datetime": local_timestamp(day, "14:00:00", timezone_name),
                    "expected_delivery_date": delivery_day.isoformat(),
                    "order_status": "SUBMITTED",
                    "ordered_by": "Manager",
                }
                purchase_orders.append(purchase_order)
                stored_items: list[dict[str, Any]] = []
                for item in sorted(delivery_items, key=lambda value: value["product_id"]):
                    po_item_source_key = f"POI-{po_source_key}-{item['product_id']}"
                    purchase_order_item = {
                        "po_item_source_key": po_item_source_key,
                        "po_source_key": po_source_key,
                        "product_id": item["product_id"],
                        "ordered_quantity": item["ordered_quantity"],
                        "order_unit": item["order_unit"],
                    }
                    purchase_order_items.append(purchase_order_item)
                    stored_items.append({**purchase_order_item, **item})
                pending_receipts[delivery_day].append(
                    {
                        "purchase_order": purchase_order,
                        "items": stored_items,
                    }
                )

    unapplied_receipt_rules = set(receipt_rules) - applied_receipt_rules
    unapplied_stocktake_rules = set(stocktake_rules) - applied_stocktake_rules
    if unapplied_receipt_rules or unapplied_stocktake_rules:
        missing = [
            *(
                f"receipt:{product_id}:{occurrence}"
                for product_id, occurrence in sorted(unapplied_receipt_rules)
            ),
            *(
                f"stocktake:{rule_date}:{product_id}"
                for rule_date, product_id in sorted(unapplied_stocktake_rules)
            ),
        ]
        raise ValueError(f"Error injection rules were not applied: {missing}")

    result = {
        "purchase_orders": purchase_orders,
        "purchase_order_items": purchase_order_items,
        "goods_receipts": goods_receipts,
        "goods_receipt_items": goods_receipt_items,
        "inventory_movements": movements,
        "stocktakes": stocktakes,
        "stocktake_items": stocktake_items,
    }
    if scenario == "errors":
        result["scenario_events"] = scenario_events
    return result
