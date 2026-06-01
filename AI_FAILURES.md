# Where the AI Was Wrong

Three concrete failures from our own testing, how we caught them, and what we did.

---

## 1. Tesseract read subtotal ₹1,110 instead of ₹1,710

**What happened:** OCR merged columns and dropped charge-line numbers. Groq/text parser saw a subtotal of ₹1,110. Person totals summed to ~₹1,026 while the printed grand total was ₹1,974.

**How we caught it:** `reconciliation.matches_bill === false` and a flag: “Your group's split is ₹1,026; bill grand total is ₹1,974.”

**Fix:**
- Switched default pipeline to **Groq vision** (`meta-llama/llama-4-scout-17b-16e-instruct`) so the model reads the image directly.
- Kept **all arithmetic in `splitter.py`**.
- Tesseract remains optional (`USE_VISION=0`) with timeouts and image resize.

---

## 2. “Item not found on receipt” when the item was on the bill

**What happened:** The text parser flagged Butter Chicken, Garlic Naan, and Sweet Lassi as missing even though they appeared in `items[]` — usually because OCR garbled names/amounts and the model lost confidence.

**How we caught it:** Yellow `flag_notes` in the UI contradicted the parsed item list.

**Fix:**
- `_clean_false_flag_notes()` removes “not found” when the item exists on the bill (including plural names like “Sweet Lassis”).
- `_supplement_assignments_from_description()` fills assignments from phrases like “Aman had…”, “Priya and Rohan shared…”, “All three shared…”.

---

## 3. Full line price for “a Masala Coke” and “2 Sweet Lassis”

**What happened:** Bill has **2** Masala Cokes (₹120) and **3** Sweet Lassis (₹270). Description says **one** coke and **two** lassis. The split charged the full line to people (e.g. ₹120 coke, ₹135 lassi each).

**How we caught it:** Manual check against the receipt image; food subtotals were too high.

**Fix (in `splitter.py`, not the LLM):**
- “a / an / one {item}” → one unit at line **rate** (₹60 coke).
- “{N} {item}” in description when shared → **N × rate**, split among sharers (2 lassis → ₹180 ÷ 2 = ₹90 each).
- Multiple people with the same exclusive item and `qty` on bill → **one unit each** (e.g. two chicken biryanis for Dev & Nikhil).
- Unassigned bill lines are **flagged**; service/GST scaled to assigned food only.

---

## Design principle

**Models extract and interpret language; Python owns money.** When the model is wrong, we **flag** or **adjust with an explicit assumption** — never a silent wrong total.
