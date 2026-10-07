# Inventory reports and approval inbox

Reports use the existing signed, tenant-scoped Inventory service and `/svc/inventory` web proxy. No schema migration or new table is required.

`GET /reports/{kind}` supports `valuation`, `reorder`, `spend`, and `margin`. Parameters: `warehouse_id` (UUID, except catalogue margin), `start` and `end` (inclusive order dates for spend), `page` (default 1), `page_size` (1–200, default 50), and `format=json|csv`.

JSON returns `{report,basis,items,total,page,page_size,totals}`. Money is returned as fixed decimal strings. Totals cover all matching rows, regardless of the selected page. CSV includes all matching rows, uses a UTF-8 BOM, and protects text cells against spreadsheet formula execution. Exports exceeding 100,000 rows return 413 and require narrower filters.

| Report | Meaning |
|---|---|
| Valuation | Physical warehouse stock on hand multiplied by current catalogue cost. Allocated and reserved units remain physical stock. Excludes stock in transit and technician stock. It is not FIFO or historical cost. |
| Reorder | Levels below their reorder point; suggested quantity reaches maximum stock after available stock and stock in transit. Estimated cost is net of VAT. Recommendations do not create purchase orders. |
| Spend | Approved, sent, partially received and received ZAR orders, filtered by order date. Committed gross includes VAT. Accepted receipt net and VAT are aggregated separately before joining orders, preventing duplicate commitment totals. This is not cash paid. |
| Margin | Prospective unit margin at current catalogue cost and retail price. Zero retail price yields an undefined percentage (`null`). This is not realized sales margin. |

`GET /approvals/inbox` requires Inventory manager access and lists the tenant's submitted/pending orders. The UI reuses existing `/purchase-orders/{id}/approve` and `/reject` decisions, including their signature, comment, role and state checks. It does not bypass purchasing approval controls.

The Inventory module includes report selection, warehouse selection, spend date filters, complete-result CSV export, pagination, and an approval inbox with signed review. Request failures are displayed as errors, not empty stock or zero financial totals.

Validation: six report tests execute actual SQL against isolated SQLite tables, covering tenant separation, complete totals across pages, warehouse filters, receipt aggregation, transit-aware reorder, undefined margin and safe CSV. The existing six PostgreSQL stock/transaction tests also pass against a disposable test database.
