# POS Usage Operations

## CSV contract

The web workflow accepts UTF-8 CSV files with these exact columns:

```text
sale_date,menu_item_id,quantity_sold,unit_price
```

Dates use `YYYY-MM-DD`, quantity is a positive whole number, and price is a nonnegative AUD amount. `menu_item_id` must match an active Product Master menu item with at least one recipe ingredient.

## Posting flow

1. The browser parses the CSV and displays a preview.
2. The API validates every row before writing.
3. Existing date and menu-item totals are skipped as duplicates.
4. New `pos_sales` rows are inserted in one transaction.
5. `post_pos_sale_usage` converts each recipe ingredient into its product inventory unit.
6. Immutable `USE` movements are inserted and the POS row is marked posted.

For example, four oat lattes using 0.25 litres each become one carton of Oat Milk usage because one carton contains one litre.

## Corrections

Posted sales cannot be edited or deleted. Operational corrections create a new inventory `ADJUSTMENT`, preserving the original POS source and movement history.
