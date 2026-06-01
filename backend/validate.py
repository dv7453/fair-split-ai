"""Validate API response matches assignment contract."""


def validate_split_response(data: dict) -> list[str]:
    errors: list[str] = []

    for key in (
        "per_person",
        "grand_total",
        "reconciliation",
        "paid_by",
        "settle_up",
        "assumptions",
        "flags",
    ):
        if key not in data:
            errors.append(f"Missing required field: {key}")

    if errors:
        return errors

    recon = data["reconciliation"]
    if not isinstance(recon, dict):
        errors.append("reconciliation must be an object")
    else:
        for key in ("sum_of_person_totals", "matches_bill"):
            if key not in recon:
                errors.append(f"reconciliation missing {key}")

    for row in data["per_person"]:
        for key in (
            "name",
            "items",
            "subtotal",
            "tax_share",
            "service_share",
            "discount_share",
            "total",
        ):
            if key not in row:
                errors.append(f"per_person row missing {key}: {row}")

    for row in data["settle_up"]:
        for key in ("from", "to", "amount"):
            if key not in row:
                errors.append(f"settle_up row missing {key}: {row}")

    if not isinstance(data["assumptions"], list):
        errors.append("assumptions must be a list")
    if not isinstance(data["flags"], list):
        errors.append("flags must be a list")

    return errors
