"""Structured splitter + parser tests for E2E scenarios 1, 3, 5, 6."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bill_validation import validate_and_repair_bill
from parser import _postprocess_parsed
from splitter import calculate_split

SCENARIO_1_DESC = (
    "Aman had Paneer Tikka, Butter Chicken, and a Masala Coke. "
    "Priya and Rohan shared Dal Makhani and Garlic Naan; they shared 2 Sweet Lassis. "
    "All three shared Jeera Rice. Priya paid."
)

SCENARIO_3_DESC = (
    "So we were eating this butter chicken and we were like seven people — "
    "Arjun, Neha, Vikram, Priya, Dev, Kavya, and Rohan — and honestly most of the "
    "naan and rice was for everyone, but Vikram and Dev kinda hogged the beers, and "
    "Neha and Priya shared the gulab jamun, Arjun had the paneer dish to himself I "
    "think? Rohan paid the whole thing."
)

SCENARIO_5_DESC = (
    "Four friends: Mia, Leo, Zoe, Sam. Mia and Leo shared the fish and chips. "
    "Zoe had the burger. Beers were for all four. Sam had both mocktails alone. "
    "The rest of us split onion rings. Leo paid. We left a 200 tip."
)

SCENARIO_6_DESC = (
    "Me and Raj and Anu, we all had dosas and vadas, coffee was mostly Raj and me. "
    "Someone paid cash, not sure who."
)


def _spice_route_parsed() -> dict:
    return {
        "items": [
            {"name": "Paneer Tikka", "amount": 280, "qty": 1},
            {"name": "Butter Chicken", "amount": 340, "qty": 1},
            {"name": "Dal Makhani", "amount": 220, "qty": 1},
            {"name": "Garlic Naan", "amount": 240, "qty": 4},
            {"name": "Jeera Rice", "amount": 240, "qty": 2},
            {"name": "Sweet Lassi", "amount": 270, "qty": 3},
            {"name": "Masala Coke", "amount": 120, "qty": 2},
        ],
        "subtotal": 1710,
        "service_charge": 171,
        "gst": 94,
        "discount": 0,
        "grand_total": 1974,
        "paid_by": "Priya",
        "all_people": ["Aman", "Priya", "Rohan"],
        "assignments": {
            "Aman": ["Paneer Tikka", "Butter Chicken", "Masala Coke"],
        },
        "shared": {
            "Dal Makhani": ["Priya", "Rohan"],
            "Garlic Naan": ["Priya", "Rohan"],
            "Sweet Lassi": ["Priya", "Rohan"],
            "Jeera Rice": ["Aman", "Priya", "Rohan"],
        },
        "source_description": SCENARIO_1_DESC,
        "flag_notes": [],
        "assumption_notes": [],
    }


def _punjab_grill_vision_stub() -> dict:
    """Typical vision output before postprocess."""
    people = ["Arjun", "Neha", "Vikram", "Priya", "Dev", "Kavya", "Rohan"]
    return {
        "items": [
            {"name": "Butter Chicken", "amount": 420, "qty": 1},
            {"name": "Dal Tadka", "amount": 280, "qty": 1},
            {"name": "Paneer Lababdar", "amount": 360, "qty": 1},
            {"name": "Garlic Naan", "amount": 330, "qty": 6},
            {"name": "Jeera Rice", "amount": 330, "qty": 3},
            {"name": "Sweet Lassi", "amount": 400, "qty": 5},
            {"name": "Kingfisher Beer (650ml)", "amount": 660, "qty": 3},
            {"name": "Gulab Jamun", "amount": 280, "qty": 4},
        ],
        "subtotal": 3060,
        "service_charge": 306,
        "gst": 168,
        "round_off": -1,
        "grand_total": 3534,
        "paid_by": "Rohan",
        "all_people": people,
        "assignments": {"Arjun": ["Paneer Lababdar"]},
        "shared": {
            "Gulab Jamun": ["Neha", "Priya"],
            "Kingfisher Beer (650ml)": ["Vikram", "Dev"],
        },
        "flag_notes": [],
        "assumption_notes": [],
    }


def _pub_vision_stub() -> dict:
    people = ["Mia", "Leo", "Zoe", "Sam"]
    return {
        "items": [
            {"name": "Fish & Chips (basket)", "amount": 680, "qty": 2},
            {"name": "Classic Veg Burger", "amount": 280, "qty": 1},
            {"name": "Beer-Battered Onion Rings", "amount": 180, "qty": 1},
            {"name": "Craft Beer Pint (IPA)", "amount": 1280, "qty": 4},
            {"name": "Virgin Mojito", "amount": 440, "qty": 2},
        ],
        "subtotal": 2860,
        "service_charge": 515,
        "gst": 168,
        "grand_total": 3543,
        "paid_by": "Leo",
        "all_people": people,
        "assignments": {
            "Sam": ["Virgin Mojito"],
            "Zoe": ["Classic Veg Burger"],
        },
        "shared": {
            "Fish & Chips (basket)": ["Mia", "Leo"],
            "Craft Beer Pint (IPA)": people,
        },
        "flag_notes": [],
        "assumption_notes": [],
    }


def _street_food_vision_stub() -> dict:
    return {
        "items": [
            {"name": "Idli Sambar", "amount": 160, "qty": 4},
            {"name": "Medu Vada", "amount": 90, "qty": 6},
            {"name": "Filter Coffee", "amount": 75, "qty": 3},
            {"name": "Masala Dosa", "amount": 160, "qty": 2},
        ],
        "subtotal": 485,
        "service_charge": 0,
        "gst": 0,
        "discount": 0,
        "grand_total": 520,
        "paid_by": None,
        "all_people": ["Raj", "Anu"],
        "assignments": {},
        "shared": {},
        "flag_notes": [
            "No service charge or GST or discount found on receipt.",
        ],
        "assumption_notes": [],
    }


def test_scenario_1_no_leftover_flags_reconciles():
    result = calculate_split(_spice_route_parsed())
    assert result["reconciliation"]["matches_bill"]
    assert result["grand_total"] == 1974
    assert not any("on bill not in description" in f.lower() for f in result["flags"])


def test_scenario_3_empty_shared_and_cgst_reconcile():
    """Vision quirk: shared:{} for lines and CGST/SGST split — must still hit ₹3534."""
    parsed = _punjab_grill_vision_stub()
    parsed["gst"] = 0
    parsed["cgst"] = 84.15
    parsed["sgst"] = 84.15
    parsed["shared"] = {
        "Gulab Jamun": ["Neha", "Priya"],
        "Kingfisher Beer (650ml)": ["Vikram", "Dev"],
        "Dal Tadka": [],
        "Garlic Naan": [],
        "Butter Chicken": [],
    }
    _postprocess_parsed(parsed, {"raw_lines": []}, SCENARIO_3_DESC)
    assert float(parsed.get("gst") or 0) >= 168
    result = calculate_split(parsed)
    assert result["reconciliation"]["matches_bill"]
    assert result["grand_total"] == 3534


def test_scenario_3_postprocess_and_reconcile():
    parsed = _punjab_grill_vision_stub()
    _postprocess_parsed(parsed, {"raw_lines": []}, SCENARIO_3_DESC)
    shared = parsed.get("shared") or {}
    assert "Butter Chicken" in shared or any(
        "butter chicken" in k.lower() for k in shared
    )
    assert any("naan" in k.lower() for k in shared)
    result = calculate_split(parsed)
    assert result["reconciliation"]["matches_bill"], (
        result["reconciliation"],
        result["flags"],
    )
    assert result["grand_total"] == 3534
    mismatch = [f for f in result["flags"] if "Person totals sum" in f]
    assert not mismatch, mismatch


def test_scenario_5_postprocess_burger_and_rings():
    parsed = _pub_vision_stub()
    _postprocess_parsed(parsed, {"raw_lines": []}, SCENARIO_5_DESC)
    assignments = parsed.get("assignments") or {}
    assert any(
        "burger" in n.lower()
        for names in assignments.values()
        for n in names
    )
    shared = parsed.get("shared") or {}
    assert any("onion" in k.lower() for k in shared)
    result = calculate_split(parsed)
    assert result["reconciliation"]["matches_bill"]
    unassigned_flags = [
        f for f in result["flags"] if "was not in your description" in f
    ]
    assert not unassigned_flags, unassigned_flags
    assert any("tip" in a.lower() for a in result["assumptions"])
    assert not any("tip" in f.lower() for f in result["flags"])
    assert not any("mocktail" in f.lower() and "align" in f.lower() for f in result["flags"])
    by = {p["name"]: p for p in result["per_person"]}
    assert by["Sam"]["subtotal"] == 805
    assert result["reconciliation"]["matches_bill"]


def test_scenario_6_packing_and_me_group():
    parsed = _street_food_vision_stub()
    _postprocess_parsed(parsed, {"raw_lines": []}, SCENARIO_6_DESC)
    assert "Me" in parsed["all_people"]
    names = [i["name"] for i in parsed["items"]]
    assert any("packing" in n.lower() for n in names)
    assert parsed["subtotal"] == 520
    tax_flags = [f for f in parsed.get("flag_notes") or [] if "no service" in f.lower()]
    assert not tax_flags
    result = calculate_split(parsed)
    assert result["reconciliation"]["matches_bill"]
    assert result["grand_total"] == 520
    packing_flags = [f for f in result["flags"] if "packing" in f.lower()]
    assert not packing_flags, packing_flags


def test_scenario_6_validate_repair_packing_only():
    parsed = _street_food_vision_stub()
    validate_and_repair_bill(parsed)
    assert any("packing" in i["name"].lower() for i in parsed["items"])
    assert float(parsed["subtotal"]) == 520


def run_all() -> None:
    test_scenario_1_no_leftover_flags_reconciles()
    test_scenario_3_empty_shared_and_cgst_reconcile()
    test_scenario_3_postprocess_and_reconcile()
    test_scenario_5_postprocess_burger_and_rings()
    test_scenario_6_packing_and_me_group()
    test_scenario_6_validate_repair_packing_only()
    print("ALL SCENARIO BILL TESTS PASSED")


if __name__ == "__main__":
    run_all()
