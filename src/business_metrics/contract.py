"""Deterministic populations for the independent DEMO-CASHFLOW contract."""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ContractError(ValueError):
    """No result may be published when a contract precondition fails."""


@dataclass(frozen=True)
class Order:
    id: str
    gross: str
    currency: str
    paid_at: str | None
    shipped_at: str | None = None


@dataclass(frozen=True)
class Refund:
    id: str
    order_id: str
    amount: str
    executed_at: str


@dataclass(frozen=True)
class Summary:
    contract: str
    month: str
    timezone: str
    currency: str
    paid_order_ids: tuple[str, ...]
    shipped_order_ids: tuple[str, ...]
    refund_ids: tuple[str, ...]
    paid_gross: Decimal
    shipped_gross: Decimal
    refunds: Decimal
    cash_net: Decimal

    def to_dict(self):
        result = dict(self.__dict__)
        for name in ["paid_gross", "shipped_gross", "refunds", "cash_net"]:
            result[name] = format(result[name], ".2f")
        for name in ["paid_order_ids", "shipped_order_ids", "refund_ids"]:
            result[name] = list(result[name])
        return result


def money(value: str) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,16}(?:\.[0-9]{1,2})?", value):
        raise ContractError("Money requires a non-negative string, at most 16 integer digits and two decimals")
    return Decimal(value).quantize(Decimal("0.01"))


def instant(value: str | None) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContractError("An event timestamp must be a timezone-aware ISO string")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("Invalid timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ContractError("Naive timestamps are forbidden")
    return result.astimezone(timezone.utc)


def unique(records, kind: str):
    seen = {}
    for record in records:
        if not isinstance(record.id, str) or not record.id.strip():
            raise ContractError(f"{kind} ID is required")
        if record.id in seen:
            raise ContractError(f"Duplicate {kind} ID")
        seen[record.id] = record
    return seen


def summarize(orders: list[Order], refunds: list[Refund], month: str, *,
              complete_sources: bool, timezone_name: str = "Europe/Paris") -> Summary:
    """Validate the entire snapshot before publishing totals.

    The caller must supply referenced orders and their complete refund history,
    including events outside the requested month. Completeness is declared,
    not inferred from the presence of records.
    """
    if complete_sources is not True:
        raise ContractError("Sources are incomplete; totals remain unavailable")
    if not isinstance(month, str) or not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", month):
        raise ContractError("Month must use YYYY-MM format")
    year, month_number = map(int, month.split("-"))
    if year < 1:
        raise ContractError("Invalid year")
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ContractError("Unknown timezone") from exc
    order_by_id = unique(orders, "order")
    unique(refunds, "refund")
    paid, shipped, selected_refunds = [], [], []
    gross_by_id, paid_at_by_id, refund_by_order = {}, {}, {}

    def belongs(timestamp):
        if timestamp is None:
            return False
        local = timestamp.astimezone(zone)
        return local.year == year and local.month == month_number

    for order in orders:
        if order.currency != "EUR":
            raise ContractError("Mixed or unsupported currency; no implicit FX conversion")
        amount = money(order.gross)
        paid_at, shipped_at = instant(order.paid_at), instant(order.shipped_at)
        if paid_at is None and (amount != 0 or shipped_at is not None):
            raise ContractError("An unpaid order cannot have captured money or a shipment")
        if paid_at is not None and shipped_at is not None and shipped_at < paid_at:
            raise ContractError("Shipment precedes payment under this demo contract")
        gross_by_id[order.id], paid_at_by_id[order.id] = amount, paid_at
        if belongs(paid_at):
            paid.append(order.id)
        if belongs(shipped_at):
            shipped.append(order.id)

    for refund in refunds:
        if refund.order_id not in order_by_id:
            raise ContractError("Refund references an unknown order")
        amount, executed_at = money(refund.amount), instant(refund.executed_at)
        paid_at = paid_at_by_id[refund.order_id]
        if executed_at is None or paid_at is None or executed_at < paid_at:
            raise ContractError("Refund must follow a known payment")
        cumulative = refund_by_order.get(refund.order_id, Decimal("0.00")) + amount
        if cumulative > gross_by_id[refund.order_id]:
            raise ContractError("Cumulative refunds exceed captured money")
        refund_by_order[refund.order_id] = cumulative
        if belongs(executed_at):
            selected_refunds.append((refund.id, amount))

    paid_total = sum((gross_by_id[key] for key in paid), Decimal("0.00"))
    shipped_total = sum((gross_by_id[key] for key in shipped), Decimal("0.00"))
    refund_total = sum((amount for _, amount in selected_refunds), Decimal("0.00"))
    return Summary("DEMO-CASHFLOW/1.0.0", month, timezone_name, "EUR",
                   tuple(sorted(paid)), tuple(sorted(shipped)),
                   tuple(sorted(key for key, _ in selected_refunds)),
                   paid_total, shipped_total, refund_total, paid_total - refund_total)
