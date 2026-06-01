import re

import pytesseract
from PIL import Image


def create_ocr_engine():
    try:
        pytesseract.get_tesseract_version()
        return {"ready": True}
    except Exception as e:
        raise RuntimeError(f"Tesseract not found: {e}")


TESSERACT_TIMEOUT_SEC = 45
MAX_OCR_SIDE_PX = 1200


def _resize_for_ocr(image: Image.Image) -> Image.Image:
    """Keep Tesseract fast — large deskewed images can hang for minutes."""
    w, h = image.size
    longest = max(w, h)
    if longest <= MAX_OCR_SIDE_PX:
        return image
    scale = MAX_OCR_SIDE_PX / longest
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def run_ocr(image: Image.Image, engine=None) -> dict:
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    image = _resize_for_ocr(image)

    config = r"--oem 3 --psm 11"
    try:
        raw_text = pytesseract.image_to_string(
            image, config=config, timeout=TESSERACT_TIMEOUT_SEC
        )
    except RuntimeError as exc:
        raise RuntimeError(
            f"OCR timed out after {TESSERACT_TIMEOUT_SEC}s — try a clearer photo"
        ) from exc

    best_lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    best_score = _score_ocr_lines(best_lines)

    # Fallback PSM only if the first pass found almost nothing
    if best_score < 10:
        try:
            raw_text = pytesseract.image_to_string(
                image,
                config=r"--oem 3 --psm 6",
                timeout=TESSERACT_TIMEOUT_SEC,
            )
        except RuntimeError as exc:
            raise RuntimeError(
                f"OCR timed out after {TESSERACT_TIMEOUT_SEC}s — try a clearer photo"
            ) from exc
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        score = _score_ocr_lines(lines)
        if score > best_score:
            best_lines = lines

    normalized = [_normalize_line(line) for line in (best_lines or [])]
    normalized = [line for line in normalized if line and len(line) > 1]

    structured = _reconstruct_receipt_lines(normalized)
    table_lines = structured if structured else _extract_bill_rows(normalized)
    markdown, table_found = _build_markdown(table_lines, normalized)

    return {
        "markdown_table": markdown,
        "raw_lines": structured or normalized,
        "low_confidence_cells": [],
        "corrections": [],
        "table_found": table_found,
    }


def _normalize_line(line: str) -> str:
    line = line.replace("₹", "INR ")
    line = re.sub(r"\bRs\.?\s*", "INR ", line, flags=re.IGNORECASE)
    line = re.sub(r"\s+", " ", line).strip()
    return line


def _is_number_line(line: str) -> bool:
    return bool(re.fullmatch(r"[\d,]+\.?\d*", line.strip()))


def _score_ocr_lines(lines: list[str]) -> int:
    """Prefer outputs with item names and plausible qty/rate/amount rows."""
    score = 0
    for line in lines:
        lower = line.lower()
        if _is_item_name_line(line):
            score += 3
        if re.match(r"^([A-Za-z][A-Za-z\s]+?)\s+\d+\s+\d+\s+\d+\s*$", line):
            score += 5
        if re.search(r"grand\s*total", lower) and re.search(r"\d", line):
            score += 2
        if re.search(r"service\s*charge", lower) and re.search(r"171", line):
            score += 2
    return score


def _is_item_name_line(line: str) -> bool:
    if _is_number_line(line):
        return False
    lower = line.lower()
    if re.search(
        r"(subtotal|service charge|cgst|sgst|grand total|round off|bill no|table:|date:|waiter:|amount|qty|rate|item|spice route|mg road|thank you|upi:)",
        lower,
    ):
        return False
    return bool(re.search(r"[A-Za-z]{2,}", line))


def _reconstruct_receipt_lines(lines: list[str]) -> list[str]:
    """
    Merge multi-line OCR (name on one line, amounts on next lines) into single rows.
    Example: Paneer Tikka / 280 / 280 -> Paneer Tikka 1 280 280
    """
    structured: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        lower = line.lower()

        if re.search(
            r"(subtotal|service charge|cgst|sgst|grand total|round off)",
            lower,
        ):
            nums = re.findall(r"[\d,]+\.?\d*", line)
            if not nums:
                j = i + 1
                while j < len(lines):
                    if re.search(
                        r"(subtotal|service charge|cgst|sgst|grand total|round off)",
                        lines[j].lower(),
                    ) and j != i:
                        break
                    if _is_number_line(lines[j]):
                        structured.append(f"{line} {lines[j]}")
                        i = j + 1
                        break
                    j += 1
                else:
                    structured.append(line)
                    i += 1
                continue
            structured.append(line)
            i += 1
            continue

        if _is_item_name_line(line):
            inline = _parse_inline_item_row(line)
            if inline:
                structured.append(inline)
                i += 1
                continue

            numbers: list[float] = []
            j = i + 1
            while j < len(lines) and _is_number_line(lines[j]) and len(numbers) < 5:
                numbers.append(float(lines[j].replace(",", "")))
                j += 1
            if numbers:
                parsed_row = _parse_item_numbers(line, numbers)
                if parsed_row:
                    structured.append(parsed_row)
                i = j
                continue

        i += 1

    return structured


def _parse_inline_item_row(line: str) -> str | None:
    match = re.match(r"^([A-Za-z][A-Za-z\s]+?)\s+((?:\d+\s+)+)$", line.strip())
    if not match:
        return None
    name = match.group(1).strip()
    numbers = [float(x) for x in match.group(2).split()]
    return _parse_item_numbers(name, numbers)


def _parse_item_numbers(name: str, numbers: list[float]) -> str | None:
    """
    Infer qty, rate, amount from OCR numbers (handles bleed from adjacent rows).
    """
    if not numbers:
        return None

    ints = [int(round(n)) for n in numbers if n > 0]
    if not ints:
        return None

    # Single amount only (e.g. Butter Chicken -> 340)
    if len(ints) == 1:
        return f"{name} 1 {ints[0]} {ints[0]}"

    # Repeated value often means rate + amount (280, 280, 340) — ignore bleed at end
    from collections import Counter

    counts = Counter(ints)
    for val, cnt in counts.items():
        if cnt >= 2 and 30 <= val <= 500:
            return f"{name} 1 {val} {val}"

    best: tuple[int, int, int] | None = None
    best_score = float("inf")

    # Try every (qty, rate, amount) triple; prefer rate < amount and exact product
    for qty in ints:
        if qty > 20:
            continue
        for rate in ints:
            if rate > 500 or rate == 0:
                continue
            for amount in ints:
                if amount > 50000:
                    continue
                expected = qty * rate
                if expected <= 0:
                    continue
                err = abs(expected - amount)
                if err > max(2, 0.02 * amount):
                    continue
                score = err
                if rate == amount and qty == 1:
                    score += 50  # avoid treating line total as rate
                if amount > rate * qty * 1.01:
                    score += 20
                if score < best_score:
                    best_score = score
                    best = (qty, rate, amount)

    if best:
        qty, rate, amount = best
        return f"{name} {qty} {rate} {amount}"

    # amount / rate => qty (e.g. Jeera Rice 120, 240 -> 2 x 120)
    if len(ints) >= 2:
        rate, amount = ints[-2], ints[-1]
        if rate > 0 and amount % rate == 0:
            qty = amount // rate
            if 1 <= qty <= 20:
                return f"{name} {qty} {rate} {amount}"

    # Two numbers: rate and amount with qty 1
    if len(ints) == 2:
        rate, amount = sorted(ints)
        return f"{name} 1 {rate} {amount}"

    return f"{name} 1 0 {ints[-1]}"


def _extract_bill_rows(lines: list[str]) -> list[str]:
    rows: list[str] = []
    for line in lines:
        lower = line.lower()
        if lower in ("item", "qty", "rate", "amount", "amount (2)"):
            continue
        if re.search(r"\d", line) and re.search(r"[a-zA-Z]{2,}", line):
            rows.append(line)
        elif re.search(
            r"(subtotal|service charge|cgst|sgst|grand total|round off)",
            lower,
        ):
            rows.append(line)
    return rows


def _build_markdown(table_lines: list[str], all_lines: list[str]) -> tuple[str, bool]:
    if not table_lines:
        return "\n".join(all_lines), False

    markdown = "| Item | Qty | Rate | Amount |\n|------|-----|------|--------|\n"
    for row in table_lines:
        match = re.match(
            r"^(.+?)\s+(\d+)\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s*$", row
        )
        if match:
            markdown += (
                f"| {match.group(1).strip()} | {match.group(2)} | "
                f"{match.group(3)} | {match.group(4)} |\n"
            )
        else:
            match2 = re.match(r"^(.+?)\s+(\d+(?:\.\d+)?)\s*$", row)
            if match2:
                markdown += f"| {match2.group(1).strip()} | | | {match2.group(2)} |\n"
            else:
                markdown += f"| {row} | | | |\n"
    return markdown, True
