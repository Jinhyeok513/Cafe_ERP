# Menu Recipe and POS Usage Design

## Scope

This data-model stage connects daily POS menu totals to ingredient inventory usage. Actual cafe menu names, prices and recipe quantities remain TBD, so production seed data is intentionally not invented.

## Recipe units

Each recipe row stores the ingredient quantity required for one sold menu item.

- When a product has physical content metadata, `recipes.ingredient_unit` must equal `products.content_unit`.
- Otherwise, `recipes.ingredient_unit` must equal `products.inventory_unit`.
- A database trigger rejects mismatched units before the recipe is saved.

Example test fixture:

```text
Oat Milk
inventory_unit = carton
content_quantity_per_inventory_unit = 1
content_unit = litre

Oat Latte recipe
ingredient_quantity = 0.25
ingredient_unit = litre
```

The inventory requirement for one sale is:

```text
inventory quantity per menu item
= ingredient quantity / content quantity per inventory unit
= 0.25 litre / 1 litre per carton
= 0.25 carton
```

Four sales therefore create one movement:

```text
USE -1 carton
source_type = POS_SALE
source_id = pos_sale_id
```

## POS grain and posting

The initial `pos_sales` grain is one date by one menu item. `quantity_sold`, the sale-date unit price and generated gross revenue are stored together.

`post_pos_sale_usage` converts every recipe ingredient into its product inventory unit and writes immutable `USE` movements. The source key prevents duplicate usage when posting is retried.

Once usage has been posted, the source sale date, menu item, quantity and price cannot be changed or deleted. Corrections must be represented by new inventory adjustments so the ledger remains auditable.

`post_pos_usage_for_date` provides the daily batch operation. It rejects the date before posting when any sold menu item has no recipe.
