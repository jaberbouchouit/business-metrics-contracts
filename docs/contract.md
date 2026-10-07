# DEMO-CASHFLOW / 1.0.0

## Business question

For a calendar month in `Europe/Paris`, identify payments, shipments and executed refunds separately, then report the net cash movement.

Every order has a unique ID, an EUR gross amount as a decimal string, an optional payment timestamp and an optional shipment timestamp. A refund has a unique ID, a referenced order, a decimal amount and an execution timestamp. All timestamps must specify an offset.

## Definitions

For month M:

- P(M) contains orders whose payment event falls in M.
- S(M) contains orders whose shipment event falls in M.
- R(M) contains refunds whose execution event falls in M.
- Paid gross sums order amounts in P(M).
- Shipped gross sums order amounts in S(M).
- Refunds sum refund amounts in R(M).
- Net cash movement = paid gross − refunds.

Month boundaries use local midnight, with the start included and the next month's start excluded. Missing timestamps are not inferred. A zero-value order with a payment event belongs to the payment population.

Example: an EUR 80 order paid in July and shipped in August contributes 80 to July paid gross and 80 to August shipped gross. An EUR 10 refund executed in August contributes 10 to August refunds. The original July payment remains present.

## Preconditions

1. `complete_sources` must be the Boolean value `true`.
2. The snapshot must include referenced orders and their full refund history, including events outside M.
3. Order IDs and refund IDs must be unique within their own populations.
4. Amounts must be non-negative strings with no more than sixteen integer digits and two fractional digits. Only EUR is supported.
5. Captured money and shipments require a known payment event. Under this demo's simplified rule, shipment cannot precede payment.
6. Refund execution must follow a known payment. Cumulative refunds cannot exceed the captured gross amount.

Any violation stops publication. The command writes a reason to stderr, writes no result to stdout and exits with code 2.

## Observable invariants

- The same snapshot produces the same result regardless of record order.
- A complete empty month has known zero amounts; an incomplete month has no result.
- Fully refunded orders remain in the original payment population.
- Across disjoint months covering all supplied events, paid gross and refunds reconcile to their respective source totals.
- Contributing IDs accompany totals, so a total can be checked against its population.

## Limits

This is an event-selection exercise, not an accounting standard. It does not calculate tax, fees, profit, cost of goods sold, recognized revenue or foreign exchange. `shipped_gross` counts the order's entire amount once; partial shipments and line allocations require another contract.

Completeness is a caller declaration. This engine does not detect missing provider pages, authenticate a source, persist frozen periods or implement a production audit trail. Those boundaries belong in a larger system with ingestion controls, versioned snapshots, access rules and review of corrections.
