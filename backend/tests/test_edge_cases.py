"""Automated edge-case tests (splitter + bill validation, no API)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bill_validation import validate_and_repair_bill
from splitter import calculate_split


def _base(**kwargs) -> dict:
    data = {
        "items": [{"name": "Item A", "amount": 100, "qty": 1}],
        "subtotal": 100,
        "service_charge": 0,
        "gst": 0,
        "discount": 0,
        "round_off": 0,
        "grand_total": 100,
        "paid_by": "Alice",
        "all_people": ["Alice", "Bob"],
        "assignments": {"Alice": ["Item A"]},
        "shared": {},
        "source_description": "",
        "flag_notes": [],
        "assumption_notes": [],
    }
    data.update(kwargs)
    return data


def test_no_service_charge():
    p = _base(service_charge=0, grand_total=100)
    r = calculate_split(p)
    assert all(row["service_share"] == 0 for row in r["per_person"])


def test_arithmetic_mismatch_flagged():
    p = _base(subtotal=100, service_charge=10, gst=5, grand_total=500)
    flags = validate_and_repair_bill(p)
    assert any("Receipt arithmetic" in f for f in flags)


def test_item_not_on_bill_zero():
    p = _base(
        assignments={"Alice": ["Item A", "Ghost Dessert"]},
        flag_notes=["Item Ghost Dessert mentioned in description not found on receipt"],
        source_description="Alice had Item A and Ghost Dessert",
    )
    r = calculate_split(p)
    assert r["per_person"][0]["subtotal"] == 100


def test_no_payer():
    p = _base(paid_by=None, source_description="Alice had Item A")
    r = calculate_split(p)
    assert r["paid_by"] is None
    assert r["settle_up"] == []
    assert any("payer" in f.lower() for f in r["flags"])


def test_subset_sharing():
    p = _base(
        items=[{"name": "Dessert", "amount": 120, "qty": 2}],
        subtotal=120,
        grand_total=120,
        all_people=["A", "B", "C", "D"],
        assignments={},
        shared={"Dessert": ["B", "C"]},
        paid_by="A",
    )
    r = calculate_split(p)
    by = {x["name"]: x for x in r["per_person"]}
    assert by["B"]["subtotal"] == 60
    assert by["C"]["subtotal"] == 60
    assert by["A"]["subtotal"] == 0


def test_three_way_split_remainder():
    p = _base(
        items=[{"name": "Shared", "amount": 100, "qty": 1}],
        subtotal=100,
        grand_total=100,
        all_people=["A", "B", "C"],
        assignments={},
        shared={"Shared": ["A", "B", "C"]},
        paid_by="A",
    )
    r = calculate_split(p)
    assert 99 <= sum(x["subtotal"] for x in r["per_person"]) <= 100


def test_discount_proportional():
    p = _base(
        subtotal=1000,
        service_charge=50,
        gst=50,
        discount=150,
        grand_total=950,
        all_people=["A", "B"],
        assignments={"A": ["Item A"], "B": []},
        shared={},
        items=[
            {"name": "Item A", "amount": 500, "qty": 1},
            {"name": "Item B", "amount": 500, "qty": 1},
        ],
    )
    p["assignments"] = {"A": ["Item A"]}
    p["shared"] = {"Item B": ["A", "B"]}
    r = calculate_split(p)
    assert any(row["discount_share"] < 0 for row in r["per_person"])
    assert r["reconciliation"]["matches_bill"]


def test_tip_flag():
    p = _base(source_description="Alice had Item A. She left a ₹50 tip.")
    r = calculate_split(p)
    assert any("tip" in a.lower() for a in r["assumptions"])
    assert not any("tip" in f.lower() for f in r["flags"])


def test_single_unit_coke():
    p = _base(
        items=[
            {"name": "Paneer", "amount": 280, "qty": 1},
            {"name": "Masala Coke", "amount": 120, "qty": 2},
        ],
        subtotal=400,
        service_charge=40,
        gst=22,
        grand_total=462,
        all_people=["Aman"],
        assignments={"Aman": ["Paneer", "Masala Coke"]},
        shared={},
        paid_by="Aman",
        source_description="Aman had Paneer and a Masala Coke.",
    )
    r = calculate_split(p)
    # 1× coke per description + 1× unclaimed coke on bill → solo diner pays both
    assert r["per_person"][0]["subtotal"] == 400
    assert r["reconciliation"]["matches_bill"]


def test_coastal_no_double_count_shared_coconut():
    """Vision often puts Tender Coconut in both assignments and shared."""
    from parser import _dedupe_exclusive_vs_shared

    desc = (
        "There were like five of us but only three ordered food — Nisha had the prawns, "
        "Rahul and I (Kiran) shared the fish curry and apps, coconuts were just for "
        "Nisha Rahul and me. Someone else paid, maybe Rahul?"
    )
    p = _base(
        items=[
            {"name": "Fish Curry", "amount": 760, "qty": 2},
            {"name": "Prawn Fry", "amount": 450, "qty": 1},
            {"name": "Appam", "amount": 100, "qty": 4},
            {"name": "Steamed Rice", "amount": 160, "qty": 2},
            {"name": "Tender Coconut", "amount": 180, "qty": 3},
        ],
        subtotal=1650,
        service_charge=165,
        gst=91,
        grand_total=1906,
        paid_by="Rahul",
        all_people=["Nisha", "Rahul", "Kiran"],
        assignments={"Nisha": ["Prawn Fry", "Tender Coconut"]},
        shared={
            "Fish Curry": ["Rahul", "Kiran"],
            "Appam": ["Nisha", "Rahul", "Kiran"],
            "Tender Coconut": ["Nisha", "Rahul", "Kiran"],
        },
        source_description=desc,
    )
    _dedupe_exclusive_vs_shared(p)
    assert "Tender Coconut" not in p["assignments"].get("Nisha", [])
    r = calculate_split(p)
    assert r["reconciliation"]["matches_bill"]
    assert r["reconciliation"]["sum_of_person_totals"] == 1906
    for person in r["per_person"]:
        assert not any(i.strip() == "Tender Coconut" for i in person["items"])


def test_coastal_unassigned_rice_splits_among_eaters():
    """Receipt 4 style: Steamed Rice on bill but not in vague description."""
    p = _base(
        items=[
            {"name": "Fish Curry", "amount": 760, "qty": 2},
            {"name": "Prawn Fry", "amount": 450, "qty": 1},
            {"name": "Appam", "amount": 100, "qty": 4},
            {"name": "Steamed Rice", "amount": 160, "qty": 2},
            {"name": "Tender Coconut", "amount": 180, "qty": 3},
        ],
        subtotal=1650,
        service_charge=165,
        gst=91,
        grand_total=1906,
        paid_by="Rahul",
        all_people=["Nisha", "Rahul", "Kiran"],
        assignments={"Nisha": ["Prawn Fry"]},
        shared={
            "Fish Curry": ["Rahul", "Kiran"],
            "Appam": ["Nisha", "Rahul", "Kiran"],
            "Tender Coconut": ["Nisha", "Rahul", "Kiran"],
        },
        source_description=(
            "There were like five of us but only three ordered food — Nisha had the prawns, "
            "Rahul and I (Kiran) shared the fish curry and apps, coconuts were just for "
            "Nisha Rahul and me. Someone else paid, maybe Rahul?"
        ),
    )
    r = calculate_split(p)
    assert r["reconciliation"]["matches_bill"]
    assert r["reconciliation"]["sum_of_person_totals"] == 1906
    assert r["paid_by"] == "Rahul"
    assert any("Steamed Rice" in a for a in r["assumptions"])


def test_infer_subtotal_from_items():
    p = _base(subtotal=0, items=[{"name": "Item A", "amount": 250, "qty": 1}])
    flags = validate_and_repair_bill(p)
    assert p["subtotal"] == 250
    assert any("inferred" in f.lower() for f in flags)


def test_rest_of_us_phrase_in_parser_output():
    """Simulates post-processed 'rest of us' shared assignment."""
    p = _base(
        items=[
            {"name": "Pasta", "amount": 320, "qty": 1},
            {"name": "Naan", "amount": 90, "qty": 1},
        ],
        subtotal=410,
        grand_total=410,
        all_people=["A", "B", "C"],
        assignments={"A": ["Pasta"]},
        shared={"Naan": ["B", "C"]},
        paid_by="C",
        source_description="A had pasta. Rest of us shared the naan.",
    )
    r = calculate_split(p)
    assert r["reconciliation"]["matches_bill"]


def run_all() -> None:
    tests = [
        test_no_service_charge,
        test_arithmetic_mismatch_flagged,
        test_item_not_on_bill_zero,
        test_no_payer,
        test_subset_sharing,
        test_three_way_split_remainder,
        test_discount_proportional,
        test_tip_flag,
        test_single_unit_coke,
        test_coastal_no_double_count_shared_coconut,
        test_coastal_unassigned_rice_splits_among_eaters,
        test_infer_subtotal_from_items,
        test_rest_of_us_phrase_in_parser_output,
    ]
    for fn in tests:
        fn()
        print(f"  ok {fn.__name__}")
    print(f"EDGE CASE TESTS PASSED ({len(tests)} cases)")


if __name__ == "__main__":
    run_all()
