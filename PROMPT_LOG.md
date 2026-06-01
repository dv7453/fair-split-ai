# Prompt Iteration Log

## v1 — Initial parser prompt

**What I tried:** A minimal Groq prompt in `parse_receipt()` — system message asked for a JSON array of `{name, price}` line items from raw OCR text only. No description input, no assignments, no bill-level fields (tax, service, discount, payer).

**What went wrong:**
- Could not split by person; output was a flat item list only.
- Model sometimes wrapped JSON in markdown fences (handled later with `_strip_markdown_fences`).
- Numbers were occasionally inferred or “fixed” when OCR was messy, with no way to flag uncertainty.
- No structured link between “who had what” in natural language and per-person totals.

---

## v2 — Full bill schema + description (`parse_bill`)

**What changed:** Replaced extraction-only prompt with a strict JSON schema: `items`, `subtotal`, `service_charge`, `gst`, `discount`, `grand_total`, `paid_by`, `assignments`, `shared`, `all_people`, plus `assumption_notes` and `flag_notes`. Added parsing rules for “rest of us”, “all of us”, missing receipt items, and “extract exact numbers — do not guess or compute”. Receipt text source: markdown table if `table_found`, else joined `raw_lines`. `temperature=0`, `max_tokens=2000`, one JSON retry on failure.

**What went wrong / still watch:**
- Occasional `assumption_notes` vs `assumption_note` naming drift in model output (schema asks for plural arrays).
- Rare invalid JSON on long receipts → retry once, then 500 with raw response in `flags`.
- Model may still *interpret* language (“rest of us”) but must not *compute* splits — that stays in `splitter.py`.

---

## v4 — Vision-first pipeline (default)

**What changed:** Default path is `parse_bill_from_image()` using `meta-llama/llama-4-scout-17b-16e-instruct` (image + description in one user message; no system message with images per Groq). Tesseract optional via `USE_VISION=0`. `splitter.py` gained description-aware portions (“a Masala Coke”, “2 Sweet Lassis”), multi-holder exclusive items, charge scaling when bill lines are unassigned, and ±₹1 grand-total reconciliation.

**What went wrong / still watch:** Vision can still miss blurry lines; unassigned bill items (e.g. 3rd lassi not in description) are flagged and grand total may not match until description covers all lines.

---

## v3 — OCR-aware inputs (no prompt text change)

**What changed:** Parser input quality improved upstream (PP-Structure table OCR, low-confidence flags merged into API `flags`, currency normalization). Prompt unchanged; reliability improved because receipt text is cleaner.

**What went wrong:** N/A for prompt itself. Residual issues are OCR-side (no table → less accurate flag) not LLM-side.

---

## Explicit answer: Did the model do the arithmetic?

**No.** The model (Groq Llama 3.3 70B) does structured extraction only:

- Reads OCR text and description
- Returns item names, amounts, who had what, who paid
- Makes language interpretations (“rest of us” → specific names)

All arithmetic is done in `splitter.py` (pure Python):

- Proportional tax/service/discount allocation
- Rounding with remainder assignment
- Settle-up calculation
- Reconciliation check

**Reason:** LLMs hallucinate numbers under pressure. Python division is exact.
