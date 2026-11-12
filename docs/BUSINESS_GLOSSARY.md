# Sales dataset business glossary (synthetic)

All data is artificially generated. The date range covers 2024–2025.

- **Order:** A record of a customer purchase attempt; orders can be `completed` or `cancelled`.
- **Gross merchandise value (GMV):** Sum of `order_items.quantity * order_items.unit_price` for completed orders only, before refunds.
- **Net revenue (simplified for this project):** Completed-order GMV minus recorded refunds. **Not** GAAP/IFRS net revenue. Refunded values must be aggregated per order before joining to item rows, or they may be double-counted.
- **Cancelled order:** Excluded from both gross and net revenue.
- **Customer segment:** `SMB`, `Mid-Market`, or `Enterprise`.
- **Region:** `North`, `South`, `East`, `West`.
- **Refund rate:** Ambiguous without a denominator: refundable-order count, refund amount / GMV, or something else. Request clarification.

## Relationships

`orders.customer_id → customers.customer_id`; `order_items.order_id → orders.order_id`; `order_items.product_id → products.product_id`; `refunds.order_id → orders.order_id`.

## Limitations

There are no taxes, shipping costs, currencies, discounts, partial shipments, or real revenue recognition rules. The synthetic data is suitable for testing SQL semantics, not drawing business conclusions.
