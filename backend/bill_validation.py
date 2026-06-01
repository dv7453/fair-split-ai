"""Validate receipt arithmetic and repair obvious parser mistakes."""

from __future__ import annotations

import re


def validate_and_repair_bill(parsed: dict) -> list[str]:
    """
    Check internal consistency of parsed bill fields.
    Repairs safe mistakes; returns new flag strings (also appended to flag_notes).
    """
    flags: list[str] = []
    items = parsed.get("items") or []

    _consolidate_tax_fields(parsed)

    items_sum = sum(float(i.get("amount") or 0) for i in items)
    subtotal = float(parsed.get("subtotal") or 0)
    service = float(parsed.get("service_charge") or 0)
    gst = float(parsed.get("gst") or 0)
    discount = float(parsed.get("discount") or 0)
    round_off = float(parsed.get("round_off") or 0)
    grand = float(parsed.get("grand_total") or 0)

    if items and subtotal <= 0:
        parsed["subtotal"] = items_sum
        subtotal = items_sum
        flags.append(f"Subtotal inferred from line items (₹{int(round(items_sum))})")

    _repair_missing_fee_lines(parsed, items, items_sum, grand, service, gst)

    items = parsed.get("items") or []
    items_sum = sum(float(i.get("amount") or 0) for i in items)
    subtotal = float(parsed.get("subtotal") or 0)

    if items and subtotal > 0:
        diff = abs(items_sum - subtotal)
        if diff > 1:
            old_subtotal = subtotal
            if diff / subtotal <= 0.08:
                parsed["subtotal"] = items_sum
                subtotal = items_sum
                if not (
                    grand > 0
                    and service <= 0
                    and gst <= 0
                    and abs(grand - items_sum) <= 1
                ):
                    flags.append(
                        f"Adjusted subtotal to match line items (₹{int(round(items_sum))}, "
                        f"was ₹{int(round(old_subtotal))})"
                    )
            else:
                flags.append(
                    f"Line items sum to ₹{int(round(items_sum))} but subtotal is "
                    f"₹{int(round(subtotal))} — difference ₹{int(round(diff))}"
                )

    if (
        grand > 0
        and service <= 0
        and gst <= 0
        and discount <= 0
        and abs(grand - items_sum) <= 1
    ):
        parsed["subtotal"] = grand
        subtotal = grand

    if grand > 0:
        computed = subtotal + service + gst - discount + round_off
        diff = abs(computed - grand)
        if diff > 1:
            flags.append(
                f"Receipt arithmetic: subtotal ₹{int(round(subtotal))} + service "
                f"₹{int(round(service))} + GST ₹{int(round(gst))}"
                f"{' − discount ₹' + str(int(round(discount))) if discount else ''}"
                f"{' + round-off ₹' + str(int(round(round_off))) if round_off else ''}"
                f" = ₹{int(round(computed))}, but grand total is ₹{int(round(grand))} "
                f"(difference ₹{int(round(diff))})"
            )
            if service <= 0 and subtotal > 0 and diff <= subtotal * 0.12:
                inferred_svc = round(diff / 1.05)
                if inferred_svc > 0:
                    parsed["service_charge"] = inferred_svc
                    flags.append(
                        f"Inferred missing service charge ≈ ₹{inferred_svc} from total gap"
                    )

    if not items:
        flags.append("No line items extracted from receipt — cannot split fairly")

    if grand <= 0:
        flags.append("Grand total missing or zero — verify receipt image")

    existing = list(parsed.get("flag_notes") or [])
    for note in flags:
        if note not in existing:
            existing.append(note)
    parsed["flag_notes"] = existing
    return flags


def _consolidate_tax_fields(parsed: dict) -> None:
    """Vision often returns CGST/SGST separately; splitter expects combined gst."""
    cgst = float(parsed.get("cgst") or 0)
    sgst = float(parsed.get("sgst") or 0)
    if cgst > 0 or sgst > 0:
        combined = cgst + sgst
        if combined > float(parsed.get("gst") or 0):
            parsed["gst"] = combined


def _repair_missing_fee_lines(
    parsed: dict,
    items: list,
    items_sum: float,
    grand: float,
    service: float,
    gst: float,
) -> None:
    """
    When printed total exceeds food lines (e.g. handwritten packing fee) and there is
    no tax, add a fee line so subtotal matches the bill total.
    """
    if grand <= 0 or service > 0 or gst > 0:
        return
    gap = grand - items_sum
    if gap <= 0 or gap > grand * 0.15:
        return
    fee_names = ("packing", "plate", "parcel", "carry", "container")
    if any(
        any(token in (item.get("name") or "").lower() for token in fee_names)
        for item in items
    ):
        return
    parsed.setdefault("items", []).append(
        {
            "name": "Packing / plates",
            "amount": round(gap, 2),
            "qty": 1,
        }
    )
    parsed["subtotal"] = grand
    notes = list(parsed.get("assumption_notes") or [])
    note = (
        f"Inferred fee line “Packing / plates” (₹{int(round(gap))}) so total matches "
        f"printed ₹{int(round(grand))}"
    )
    if note not in notes:
        notes.append(note)
    parsed["assumption_notes"] = notes
