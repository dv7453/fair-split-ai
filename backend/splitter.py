import re


def normalize(s: str) -> str:
    return s.lower().strip()


def calculate_split(parsed: dict) -> dict:
    """
    Compute per-person bill split from parse_bill() output using proportional fairness rules.
    Pure Python — no AI.
    """
    flags: list[str] = list(parsed.get("flag_notes") or [])
    assumptions: list[str] = list(parsed.get("assumption_notes") or [])
    description: str = parsed.get("source_description") or ""

    if description and re.search(r"\btip\b", description, re.I):
        tip_note = (
            "Tip mentioned in description — not included in split unless it "
            "appears on the printed receipt total"
        )
        if not any("tip" in a.lower() for a in assumptions):
            assumptions.append(tip_note)

    all_people: list[str] = list(parsed.get("all_people") or [])
    assignments: dict = parsed.get("assignments") or {}
    shared: dict = parsed.get("shared") or {}
    items_list: list[dict] = parsed.get("items") or []
    catalog = _build_item_catalog(items_list)

    assigned_keys = _assigned_catalog_keys(catalog, assignments, shared)

    if not assignments and not shared:
        flags.append("No item assignments found — check description")

    grand_total_raw = parsed.get("grand_total")
    if grand_total_raw is None or grand_total_raw == 0:
        flags.append("Could not read grand total from receipt")
    grand_total = int(round(float(grand_total_raw or 0)))

    receipt_subtotal = float(parsed.get("subtotal") or 0)
    discount_total = int(round(float(parsed.get("discount") or 0)))
    service_charge_total = int(round(float(parsed.get("service_charge") or 0)))
    gst_total = int(round(float(parsed.get("gst") or 0)))

    if discount_total > receipt_subtotal > 0:
        flags.append(
            f"Discount (₹{discount_total}) exceeds subtotal (₹{int(round(receipt_subtotal))}) — check receipt"
        )

    paid_by = parsed.get("paid_by")

    shared_only_keys = {
        normalize(name)
        for name in shared
        if _resolve_catalog_entry(name, catalog, []) is not None
    }
    for name in shared:
        entry = _resolve_catalog_entry(name, catalog, [])
        if entry:
            shared_only_keys.add(normalize(entry["name"]))

    # STEP 1 — per-person food subtotals
    food_subtotal: dict[str, float] = {person: 0.0 for person in all_people}
    person_items: dict[str, list[str]] = {person: [] for person in all_people}

    for person in all_people:
        for item_name in assignments.get(person, []):
            entry = _resolve_catalog_entry(item_name, catalog, [])
            if entry and normalize(entry["name"]) in shared_only_keys:
                continue
            amount, label = _food_amount_for_person(
                item_name,
                person,
                exclusive=True,
                share_count=1,
                description=description,
                catalog=catalog,
                assignments=assignments,
                flags=flags,
                assumptions=assumptions,
            )
            food_subtotal[person] += amount
            person_items[person].append(label)

        for item_name, sharers in shared.items():
            if person not in sharers:
                continue
            share_count = len(sharers)
            if share_count == 0:
                continue
            amount, label = _food_amount_for_person(
                item_name,
                person,
                exclusive=False,
                share_count=share_count,
                description=description,
                catalog=catalog,
                assignments=assignments,
                flags=flags,
                assumptions=assumptions,
            )
            food_subtotal[person] += amount
            person_items[person].append(label)

    for person in all_people:
        if food_subtotal[person] == 0:
            flags.append(f"Person {person} has no items assigned")

    unassigned_food, unassigned_labels = _allocate_unassigned_line_items(
        catalog=catalog,
        assigned_keys=assigned_keys,
        all_people=all_people,
        food_subtotal=food_subtotal,
        assumptions=assumptions,
        flags=flags,
    )
    for person in all_people:
        food_subtotal[person] += unassigned_food.get(person, 0.0)
        person_items[person].extend(unassigned_labels.get(person, []))

    leftover_food, leftover_labels = _allocate_leftover_units(
        catalog=catalog,
        assignments=assignments,
        shared=shared,
        all_people=all_people,
        food_subtotal=food_subtotal,
        description=description,
        assumptions=assumptions,
    )
    for person in all_people:
        food_subtotal[person] += leftover_food.get(person, 0.0)
        person_items[person].extend(leftover_labels.get(person, []))

    total_food_subtotal = sum(food_subtotal.values())
    if total_food_subtotal == 0:
        bill_items = [item.get("name", "") for item in items_list]
        raise ValueError(
            "No items assigned to anyone. "
            f"Bill items: {bill_items}. "
            f"Assignments: {assignments}. "
            f"Shared: {shared}. "
            "Use the exact item names from the bill in your description, or fix the parser output."
        )

    items_food_total = sum(float(entry["amount"]) for entry in catalog.values())
    food_gap = max(receipt_subtotal, items_food_total) - total_food_subtotal
    if food_gap > 1.0:
        recipients = list(all_people)
        if not recipients:
            recipients = [
                person for person in all_people if food_subtotal[person] > 0
            ]
        share = food_gap / len(recipients)
        assumptions.append(
            f"₹{int(round(food_gap))} of food on the bill was not fully assigned from "
            f"the description — split equally among {', '.join(recipients)}"
        )
        for person in recipients:
            food_subtotal[person] += share
            person_items[person].append(
                f"Unassigned food (1/{len(recipients)})"
            )
        total_food_subtotal = sum(food_subtotal.values())

    # Scale bill-level charges only when food still below bill subtotal after repair
    charge_scale = 1.0
    if receipt_subtotal > 0 and total_food_subtotal < receipt_subtotal * 0.995:
        charge_scale = total_food_subtotal / receipt_subtotal
        assumptions.append(
            f"Service charge and GST scaled to {charge_scale:.2%} of bill "
            f"(only assigned food ₹{int(round(total_food_subtotal))} of "
            f"₹{int(round(receipt_subtotal))} subtotal)"
        )
    effective_service = int(round(service_charge_total * charge_scale))
    effective_gst = int(round(gst_total * charge_scale))
    effective_discount = int(round(discount_total * charge_scale))

    # STEP 2 — proportions
    proportion = {
        person: food_subtotal[person] / total_food_subtotal for person in all_people
    }

    # STEPS 3–5 — allocate charges with remainder adjustment on largest share
    discount_share, discount_note = _allocate_proportional(
        effective_discount, proportion, all_people, negative=True
    )
    service_share, service_note = _allocate_proportional(
        effective_service, proportion, all_people, negative=False
    )
    gst_share, gst_note = _allocate_proportional(
        effective_gst, proportion, all_people, negative=False
    )

    for note in (discount_note, service_note, gst_note):
        if note:
            assumptions.append(note)

    # STEP 6 — totals
    total: dict[str, int] = {}
    for person in all_people:
        total[person] = (
            round(food_subtotal[person])
            + discount_share[person]
            + service_share[person]
            + gst_share[person]
        )

    # STEP 7 — reconciliation (printed totals often round per line / tax)
    sum_of_totals = sum(total.values())
    bill_remainder = grand_total - sum_of_totals
    max_remainder_fix = max(5, len(all_people))
    if bill_remainder != 0 and abs(bill_remainder) <= max_remainder_fix:
        adjust_person = max(all_people, key=lambda person: total[person])
        total[adjust_person] += bill_remainder
        sum_of_totals = sum(total.values())
        assumptions.append(
            f"Bill total reconciliation: ₹{abs(bill_remainder)} "
            f"{'added to' if bill_remainder > 0 else 'deducted from'} "
            f"{adjust_person}'s total to match printed grand total"
        )

    matches_bill = sum_of_totals == grand_total
    if not matches_bill:
        if abs(sum_of_totals - grand_total) > 1:
            flags.append(
                f"Person totals sum to ₹{sum_of_totals}; bill grand total is ₹{grand_total} "
                f"(difference ₹{abs(sum_of_totals - grand_total)} — check receipt amounts)."
            )

    # STEP 8 — settle up
    settle_up: list[dict[str, str | int]] = []
    if paid_by is None:
        flags.append("No payer stated — settle-up not calculated")
    elif len(all_people) <= 1:
        settle_up = []
    else:
        for person in all_people:
            if person != paid_by:
                settle_up.append(
                    {"from": person, "to": paid_by, "amount": total[person]}
                )

    # STEP 9 — per-person output
    per_person = [
        {
            "name": person,
            "items": person_items[person],
            "subtotal": round(food_subtotal[person]),
            "tax_share": gst_share[person],
            "service_share": service_share[person],
            "discount_share": discount_share[person],
            "total": total[person],
        }
        for person in all_people
    ]

    deduped_assumptions: list[str] = []
    seen_assumptions: set[str] = set()
    for note in assumptions:
        if note not in seen_assumptions:
            seen_assumptions.add(note)
            deduped_assumptions.append(note)

    return {
        "per_person": per_person,
        "grand_total": grand_total,
        "reconciliation": {
            "sum_of_person_totals": sum_of_totals,
            "matches_bill": matches_bill,
        },
        "paid_by": paid_by,
        "settle_up": settle_up,
        "assumptions": deduped_assumptions,
        "flags": flags,
    }


def _assigned_catalog_keys(
    catalog: dict[str, dict],
    assignments: dict,
    shared: dict,
) -> set[str]:
    keys: set[str] = set()
    for names in assignments.values():
        for name in names:
            entry = _resolve_catalog_entry(name, catalog, [])
            if entry:
                keys.add(normalize(entry["name"]))
    for item_name, sharers in shared.items():
        if not sharers:
            continue
        entry = _resolve_catalog_entry(item_name, catalog, [])
        if entry:
            keys.add(normalize(entry["name"]))
    return keys


def _allocate_unassigned_line_items(
    *,
    catalog: dict[str, dict],
    assigned_keys: set[str],
    all_people: list[str],
    food_subtotal: dict[str, float],
    assumptions: list[str],
    flags: list[str],
) -> tuple[dict[str, float], dict[str, list[str]]]:
    """Bill lines never mentioned in description — split among people who did order."""
    extra: dict[str, float] = {person: 0.0 for person in all_people}
    labels: dict[str, list[str]] = {person: [] for person in all_people}

    recipients = list(all_people)
    if not recipients:
        return extra, labels

    for key, entry in catalog.items():
        if key in assigned_keys:
            continue
        name = entry["name"]
        pool = float(entry["amount"])
        share = pool / len(recipients)
        assumptions.append(
            f"{name} (₹{int(round(pool))}) not in description — "
            f"split among {', '.join(recipients)}"
        )
        for person in recipients:
            extra[person] += share
            labels[person].append(f"{name} (1/{len(recipients)})")

    return extra, labels


def _build_item_catalog(items_list: list[dict]) -> dict[str, dict]:
    catalog: dict[str, dict] = {}
    for item in items_list:
        name = item.get("name", "")
        if not name:
            continue
        qty = max(1, int(item.get("qty") or 1))
        amount = float(item.get("amount") or 0)
        rate = amount / qty if qty else amount
        catalog[normalize(name)] = {
            "name": name,
            "qty": qty,
            "amount": amount,
            "rate": rate,
        }
    return catalog


def _resolve_catalog_entry(item_name: str, catalog: dict[str, dict], flags: list[str]) -> dict | None:
    key = normalize(item_name)
    if key in catalog:
        return catalog[key]
    for cat_key, entry in catalog.items():
        if key in cat_key or cat_key in key:
            flags.append(f"Matched '{item_name}' to bill item '{entry['name']}' (fuzzy)")
            return entry
    flags.append(
        f"Item '{item_name}' not found on bill — assigned ₹0"
    )
    return None


def _normalize_item_key(name: str) -> str:
    return re.sub(r"\s+", " ", name.lower().strip())


def _flex_name_pattern(item_name: str) -> str:
    """Regex fragment that matches singular/plural item names in description."""
    key = _normalize_item_key(item_name)
    if key.endswith("s"):
        stem = re.escape(key[:-1])
        return rf"{stem}s?"
    return rf"{re.escape(key)}s?"


def _described_unit_count(item_name: str, description: str) -> int | None:
    if not description.strip():
        return None
    flex = _flex_name_pattern(item_name)
    match = re.search(rf"(\d+)\s+{flex}", description, re.I)
    if match:
        return int(match.group(1))
    word_nums = {
        "two": 2,
        "three": 3,
        "four": 4,
    }
    for word, num in word_nums.items():
        if re.search(rf"\b{word}\s+{flex}", description, re.I):
            return num
    return None


def _is_single_unit_mentioned(item_name: str, description: str) -> bool:
    if not description.strip():
        return False
    flex = _flex_name_pattern(item_name)
    # "Dev and Nikhil each had a chicken biryani" → one per person, not one total
    if re.search(rf"\beach\b.{0,120}?\b(?:a|an|one)\s+{flex}", description, re.I):
        return False
    if re.search(rf"\b(?:a|an|one)\s+{flex}.{0,40}?\beach\b", description, re.I):
        return False
    return bool(re.search(rf"\b(?:a|an|one)\s+{flex}", description, re.I))


def _allocate_leftover_units(
    *,
    catalog: dict[str, dict],
    assignments: dict,
    shared: dict,
    all_people: list[str],
    food_subtotal: dict[str, float],
    description: str,
    assumptions: list[str],
) -> tuple[dict[str, float], dict[str, list[str]]]:
    """
    Bill qty can exceed what the description claims (e.g. 2 cokes, 'a Masala Coke').
    Split unclaimed units so food + charges reconcile to the printed grand total.
    """
    extra: dict[str, float] = {person: 0.0 for person in all_people}
    labels: dict[str, list[str]] = {person: [] for person in all_people}

    assigned_keys: set[str] = set()
    for names in assignments.values():
        for name in names:
            entry = _resolve_catalog_entry(name, catalog, [])
            if entry:
                assigned_keys.add(normalize(entry["name"]))

    shared_by_key: dict[str, list[str]] = {}
    for item_name, sharers in shared.items():
        entry = _resolve_catalog_entry(item_name, catalog, [])
        if entry:
            key = normalize(entry["name"])
            assigned_keys.add(key)
            shared_by_key[key] = list(sharers)

    for key, entry in catalog.items():
        if key not in assigned_keys:
            continue

        name = entry["name"]
        qty = entry["qty"]
        rate = entry["rate"]
        if qty <= 1:
            continue

        leftover = 0
        recipients: list[str] = list(all_people)

        in_assignments = any(
            normalize(n) == key or key in normalize(n) or normalize(n) in key
            for names in assignments.values()
            for n in names
        )

        eaters = [p for p in all_people if food_subtotal.get(p, 0) > 0] or list(
            all_people
        )

        if in_assignments and _is_single_unit_mentioned(name, description):
            holders = _exclusive_holder_count(name, assignments)
            if holders > 1 and holders <= qty:
                leftover = 0
            else:
                leftover = qty - 1
                recipients = eaters
        elif key in shared_by_key:
            unit_count = _described_unit_count(name, description)
            if unit_count is not None and unit_count < qty:
                leftover = qty - unit_count
                recipients = [p for p in shared_by_key[key] if p in all_people]
                if not recipients:
                    recipients = list(all_people)

        if leftover <= 0 or not recipients:
            continue

        pool = leftover * rate
        share = pool / len(recipients)
        recipient_names = ", ".join(recipients)
        assumptions.append(
            f"{leftover}× {name} on bill not in description (₹{int(round(pool))}) "
            f"split among {recipient_names}"
        )
        for person in recipients:
            extra[person] += share
            if len(recipients) == 1:
                labels[person].append(f"{name} (unclaimed)")
            else:
                labels[person].append(
                    f"{name} (unclaimed {leftover}×, 1/{len(recipients)})"
                )

    return extra, labels


def _exclusive_holder_count(item_name: str, assignments: dict) -> int:
    key = normalize(item_name)
    count = 0
    for names in assignments.values():
        for name in names:
            n = normalize(name)
            if n == key or key in n or n in key:
                count += 1
    return count


def _food_amount_for_person(
    item_name: str,
    person: str,
    *,
    exclusive: bool,
    share_count: int,
    description: str,
    catalog: dict[str, dict],
    assignments: dict,
    flags: list[str],
    assumptions: list[str],
) -> tuple[float, str]:
    entry = _resolve_catalog_entry(item_name, catalog, flags)
    if entry is None:
        return 0.0, item_name

    name = entry["name"]
    rate = entry["rate"]
    qty = entry["qty"]
    line_total = entry["amount"]
    unit_count = _described_unit_count(name, description)

    if exclusive:
        holders = _exclusive_holder_count(name, assignments)
        if holders > 1 and holders <= qty:
            assumptions.append(
                f"{person}: 1× {name} at ₹{int(round(rate))} "
                f"({holders} people, qty {qty} on bill)"
            )
            return rate, name
        if _is_single_unit_mentioned(name, description) and qty > 1:
            assumptions.append(
                f"{person}: counted 1× {name} at ₹{int(round(rate))} "
                f"(description says 'a/{name}', bill line is qty {qty})"
            )
            return rate, name
        if unit_count is not None and unit_count < qty:
            amount = rate * unit_count
            assumptions.append(
                f"{person}: {unit_count}× {name} at ₹{int(round(amount))} per description"
            )
            return amount, f"{name} ({unit_count}×)"
        return line_total, name

    # Shared item
    if unit_count is not None:
        units = min(unit_count, qty)
        pool = rate * units
        if units < qty:
            assumptions.append(
                f"Shared {units} of {qty}× {name} (₹{int(round(pool))}) per description"
            )
        share = pool / share_count
        if units == 1:
            return share, f"{name} (1/{share_count})"
        return share, f"{name} ({units}×, 1/{share_count})"

    share = line_total / share_count
    return share, f"{name} (1/{share_count})"


def _allocate_proportional(
    charge_total: int,
    proportion: dict[str, float],
    people: list[str],
    *,
    negative: bool,
) -> tuple[dict[str, int], str | None]:
    """Allocate a charge proportionally with rounding; fix remainder on largest share."""
    if charge_total == 0:
        return {person: 0 for person in people}, None

    if negative:
        shares = {
            person: -round(charge_total * proportion[person]) for person in people
        }
        target = -charge_total
    else:
        shares = {
            person: round(charge_total * proportion[person]) for person in people
        }
        target = charge_total

    remainder = target - sum(shares.values())
    if remainder == 0:
        return shares, None

    adjust_person = max(people, key=lambda person: abs(shares[person]))
    shares[adjust_person] += remainder

    charge_label = "discount" if negative else "charge"
    return shares, (
        f"Rounding remainder of ₹{abs(remainder)} for {charge_label} "
        f"applied to {adjust_person}"
    )


def split_bill(items: list[dict], people: int = 1) -> dict:
    """Compute per-person share for parsed receipt items (legacy helper)."""
    if people < 1:
        people = 1

    subtotal = sum(item.get("price", 0) for item in items)
    per_person = round(subtotal / people, 2)

    return {
        "subtotal": round(subtotal, 2),
        "people": people,
        "per_person": per_person,
        "items": items,
    }
