"""Splitter tests for assignment sample bills R1–R4 (structured input, no LLM)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from splitter import calculate_split


def _r1_parsed() -> dict:
    return {
        "items": [
            {"name": "Cappuccino", "amount": 180, "qty": 1},
            {"name": "Grilled Chicken Sandwich", "amount": 260, "qty": 1},
            {"name": "Penne Arrabiata", "amount": 320, "qty": 1},
            {"name": "Fresh Lime Soda", "amount": 120, "qty": 1},
            {"name": "Brownie", "amount": 160, "qty": 1},
        ],
        "subtotal": 1040,
        "service_charge": 52,
        "gst": 55,
        "discount": 0,
        "grand_total": 1147,
        "paid_by": "Sameer",
        "all_people": ["Ravi", "Neha", "Sameer"],
        "assignments": {
            "Ravi": ["Cappuccino", "Grilled Chicken Sandwich"],
            "Neha": ["Penne Arrabiata", "Fresh Lime Soda"],
            "Sameer": ["Brownie"],
        },
        "shared": {},
        "source_description": (
            "Three of us — Ravi, Neha, Sameer. Ravi had the cappuccino and the sandwich. "
            "Neha had the pasta and the lime soda. Sameer had the brownie. Sameer paid."
        ),
        "flag_notes": [],
        "assumption_notes": [],
    }


def _r2_parsed() -> dict:
    return {
        "items": [
            {"name": "Paneer Butter Masala", "amount": 320, "qty": 1},
            {"name": "Dal Makhani", "amount": 260, "qty": 1},
            {"name": "Butter Naan", "amount": 240, "qty": 4},
            {"name": "Jeera Rice", "amount": 180, "qty": 1},
            {"name": "Gulab Jamun", "amount": 120, "qty": 2},
            {"name": "Masala Papad", "amount": 100, "qty": 2},
        ],
        "subtotal": 1220,
        "service_charge": 61,
        "gst": 64,
        "discount": 0,
        "grand_total": 1345,
        "paid_by": "Priya",
        "all_people": ["Aman", "Priya", "Karan", "Sara"],
        "assignments": {},
        "shared": {
            "Paneer Butter Masala": ["Aman", "Priya", "Karan", "Sara"],
            "Dal Makhani": ["Aman", "Priya", "Karan", "Sara"],
            "Butter Naan": ["Aman", "Priya", "Karan", "Sara"],
            "Jeera Rice": ["Aman", "Priya", "Karan", "Sara"],
            "Masala Papad": ["Aman", "Priya", "Karan", "Sara"],
            "Gulab Jamun": ["Priya", "Karan"],
        },
        "source_description": (
            "Four of us: Aman, Priya, Karan, Sara. The Gulab Jamun was shared just "
            "by Priya and Karan. Everything else was common to all four. Priya paid."
        ),
        "flag_notes": [],
        "assumption_notes": [],
    }


def _r3_parsed() -> dict:
    return {
        "items": [
            {"name": "Margherita Pizza", "amount": 380, "qty": 1},
            {"name": "Arrabiata Pasta", "amount": 340, "qty": 1},
            {"name": "Garlic Bread", "amount": 160, "qty": 1},
            {"name": "Craft Beer", "amount": 500, "qty": 2},
            {"name": "Virgin Mojito", "amount": 180, "qty": 1},
        ],
        "subtotal": 1560,
        "service_charge": 78,
        "gst": 82,
        "discount": 0,
        "grand_total": 1720,
        "paid_by": "Rohit",
        "all_people": ["Ishaan", "Meera", "Rohit"],
        "assignments": {
            "Meera": ["Virgin Mojito"],
        },
        "shared": {
            "Margherita Pizza": ["Ishaan", "Meera", "Rohit"],
            "Arrabiata Pasta": ["Ishaan", "Meera", "Rohit"],
            "Garlic Bread": ["Ishaan", "Meera", "Rohit"],
            "Craft Beer": ["Ishaan", "Rohit"],
        },
        "source_description": (
            "Ishaan, Meera, Rohit. Pizza, pasta and garlic bread shared equally by all "
            "three. The two beers were Ishaan and Rohit only. The mojito was Meera's. Rohit paid."
        ),
        "flag_notes": [],
        "assumption_notes": [],
    }


def _r4_parsed() -> dict:
    return {
        "items": [
            {"name": "Chicken Biryani", "amount": 560, "qty": 2},
            {"name": "Veg Biryani", "amount": 240, "qty": 1},
            {"name": "Mutton Rogan Josh", "amount": 420, "qty": 1},
            {"name": "Raita", "amount": 120, "qty": 2},
            {"name": "Soft Drinks", "amount": 180, "qty": 3},
        ],
        "subtotal": 1520,
        "service_charge": 76,
        "gst": 68,
        "discount": 228,
        "grand_total": 1436,
        "paid_by": "Anjali",
        "all_people": ["Dev", "Nikhil", "Anjali", "Farah"],
        "assignments": {
            "Dev": ["Chicken Biryani"],
            "Nikhil": ["Chicken Biryani"],
            "Anjali": ["Veg Biryani"],
            "Farah": ["Mutton Rogan Josh"],
        },
        "shared": {
            "Raita": ["Dev", "Nikhil", "Anjali", "Farah"],
            "Soft Drinks": ["Dev", "Nikhil", "Anjali", "Farah"],
        },
        "source_description": (
            "Dev and Nikhil each had a chicken biryani. Anjali had the veg biryani. "
            "Farah had the rogan josh. The raita and soft drinks were common to all four. "
            "We used a 15% off coupon. Anjali paid."
        ),
        "flag_notes": [],
        "assumption_notes": [],
    }


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
        "source_description": (
            "Aman had Paneer Tikka, Butter Chicken, and a Masala Coke. "
            "Priya and Rohan shared Dal Makhani and Garlic Naan; they shared 2 Sweet Lassis. "
            "All three shared Jeera Rice. Priya paid."
        ),
        "flag_notes": [],
        "assumption_notes": [],
    }


def test_r1_reconciles():
    result = calculate_split(_r1_parsed())
    assert result["reconciliation"]["matches_bill"]
    assert result["grand_total"] == 1147
    assert len(result["settle_up"]) == 2


def test_r2_reconciles():
    result = calculate_split(_r2_parsed())
    assert result["reconciliation"]["matches_bill"]
    assert result["grand_total"] == 1345


def test_r3_reconciles_and_beer_split():
    result = calculate_split(_r3_parsed())
    assert result["reconciliation"]["matches_bill"]
    by_name = {p["name"]: p for p in result["per_person"]}
    assert by_name["Ishaan"]["subtotal"] == by_name["Rohit"]["subtotal"]


def test_r4_reconciles_with_discount():
    result = calculate_split(_r4_parsed())
    assert result["reconciliation"]["matches_bill"]
    assert result["grand_total"] == 1436
    assert any(p["discount_share"] < 0 for p in result["per_person"])


def test_r4_no_false_chicken_biryani_flag():
    """Qty 2 on bill + 'each had a chicken biryani' for Dev and Nikhil must not flag."""
    result = calculate_split(_r4_parsed())
    chicken_flags = [f for f in result["flags"] if "chicken biryani" in f.lower()]
    assert not chicken_flags, chicken_flags
    by_name = {p["name"]: p for p in result["per_person"]}
    assert by_name["Dev"]["subtotal"] == by_name["Nikhil"]["subtotal"] == 280


def test_spice_route_fractional_items():
    result = calculate_split(_spice_route_parsed())
    by_name = {p["name"]: p for p in result["per_person"]}
    # 760 + 20 unclaimed coke share; 400 + 20 coke + 45 unclaimed lassi each
    assert by_name["Aman"]["subtotal"] == 780
    assert by_name["Priya"]["subtotal"] == 465
    assert by_name["Rohan"]["subtotal"] == 465
    assert result["reconciliation"]["matches_bill"]
    assert result["reconciliation"]["sum_of_person_totals"] == 1974
    leftover_flags = [
        f for f in result["flags"] if "on bill not in description" in f.lower()
    ]
    assert not leftover_flags, leftover_flags
    assert by_name["Aman"]["total"] == 900
    assert by_name["Priya"]["total"] == 537
    assert by_name["Rohan"]["total"] == 537


def run_all() -> None:
    test_r1_reconciles()
    test_r2_reconciles()
    test_r3_reconciles_and_beer_split()
    test_r4_reconciles_with_discount()
    test_spice_route_fractional_items()
    print("ALL TESTS PASSED (no server required)")


if __name__ == "__main__":
    run_all()
