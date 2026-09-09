# Inventory Ledger and Stocktake Design

## Product quantities

`products.inventory_unit` defines how stock quantities are interpreted throughout the ledger and stocktake tables. It represents the unit a manager counts during normal cafe operations, such as `bottle`, `carton`, `bag` or `each`.

`products.content_quantity_per_inventory_unit` and `products.content_unit` preserve physical volume or weight for recipe calculations. They do not change the displayed inventory unit.

`products.pack_size` converts an order unit into inventory units:

```text
received inventory quantity = accepted order quantity * pack_size
```

Examples:

```text
Oat Milk: 6 accepted cartons * 1 = RECEIVE +6 carton
Eggs: 9 accepted trays * 25 = RECEIVE +225 each
```

## Inventory movements

One `inventory_movements` row represents one stock change for one product. `quantity_change` is signed and always expressed in the product's `inventory_unit`.

| Movement type | Required sign | Example |
|---|---:|---:|
| `RECEIVE` | Positive | `+6 carton` |
| `USE` | Negative | `-2.4 carton` |
| `WASTE` | Negative | `-3 each` |
| `ADJUSTMENT` | Positive or negative, excluding zero | `-0.6 carton` |

Current stock is calculated as:

```text
SUM(inventory_movements.quantity_change)
```

Movement rows cannot be updated or deleted. A correction is recorded as a new `ADJUSTMENT` movement with a reason and source reference.

## Receiving discrepancies

Goods receipt quantities remain in the purchase order unit. Only `accepted_quantity` is converted and posted to inventory.

The main synthetic receiving problems are:

- `SHORT_DELIVERY`
- `MISSING_ITEM`
- `WRONG_PRODUCT`

`DAMAGED` remains supported but should be uncommon in generated data. A wrong product or missing item has zero accepted quantity and creates no inventory receipt for the ordered product.

Receipt posting is idempotent. Reposting the same receipt item cannot create a duplicate inventory movement.

## Stocktake reconciliation

When a count is recorded, the system stores both the physical quantity and the current ledger quantity in the product's inventory unit.

```text
variance = physical_quantity - system_quantity
```

Reconciliation creates one `ADJUSTMENT` movement for each non-zero variance:

```text
movement_type = ADJUSTMENT
source_type = STOCKTAKE
source_id = stocktake_item_id
reason_code = STOCKTAKE_CORRECTION
quantity_change = variance
```

Reconciliation is also idempotent, so retrying the operation does not duplicate corrections.

## Source tracking

`source_type` and `source_id` identify the operational record that produced a movement. `receipt_item_id` is additionally enforced as a direct foreign key for receipt movements. Future POS and recipe tables will use the same source pattern for ingredient usage.
