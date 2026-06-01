# Prompt Iteration Log

## v1 — Legacy line-item extractor (`parse_receipt`)

**Prompt:**
Extract receipt line items as JSON array. Each item: {"name": str, "price": float}.
Return only valid JSON.

Input: raw OCR text only. No description, no assignments, no tax/service/payer.

**What went wrong:**
- Flat item list only — no way to split by person
- Model occasionally wrapped output in markdown fences
- Numbers inferred when OCR was messy, no way to flag uncertainty
- JSON failures fell through to a regex fallback (`_fallback_parse`) with no LLM recovery

This version is still in `parser.py` but is never called by the API.

---

## v2 — Full schema parser: OCR + description (`parse_bill`)

**What changed:** Replaced extraction-only prompt with a strict JSON schema covering `items`, `subtotal`, `service_charge`, `gst`, `discount`, `grand_total`, `paid_by`, `assignments`, `shared`, `all_people`, `assumption_notes`, `flag_notes`.

Added description as a second input. Key rules added to prompt:

- "Extract exact numbers from the receipt text — do not guess or compute"
- "NEVER invent line items not visible on the receipt"
- "If an item appears in description but NOT in the receipt, set a flag_note"
- "If description mentions a tip, add flag_note: Tip mentioned — not included in split unless on receipt"

Note: the system prompt string still says "receipt image" even on the OCR path where the user message contains OCR text — cosmetic mismatch, no functional impact.

**Model:** `llama-3.3-70b-versatile`, `temperature=0`, `max_tokens=2000`

**What went wrong:**
- Model occasionally returned `assumption_note` (singular) instead of `assumption_notes` (array) — fixed with `_validate_parsed()` normalization
- Invalid JSON on long receipts → added one retry, then 500 with raw response in `flags`
- Model emitted false "item not found on receipt" flags for items that *were* on the bill — fixed with `_clean_false_flag_notes()`
- Model skipped assignments for items mentioned implicitly in description — fixed with `_supplement_assignments_from_description()`
- Occasional empty `shared: {"Naan": []}` blocked allocation entirely — fixed with `_strip_empty_shared()`

---

## v3 — OCR upstream (no prompt change)

**What changed:** Improved input quality via Tesseract OCR pipeline with OpenCV preprocessing (CLAHE contrast, deskew, denoise, upscale). Receipt text arrives as a markdown table when structure is detected, or raw lines as fallback. Currency symbols normalized (₹/Rs./INR → `INR `).

API appends flag `"No table structure detected — results may be less accurate"` when table parsing fails.

**Prompt unchanged.** Reliability improved because the model received cleaner input.

Note: `PROMPT_LOG.md` and `EDGE_CASES.md` reference PP-Structure/PaddleOCR. That was the planned implementation — switched to Tesseract after PaddleOCR caused full CPU thermal throttling on M2 (10+ minutes per inference, unusable). Tesseract with preprocessing gives comparable accuracy on printed receipts.

---

## v4 — Vision-first pipeline (current default)

**What changed:** Default path switched to direct image inference via `parse_bill_from_image()` using `meta-llama/llama-4-scout-17b-16e-instruct`.

Image sent as base64 JPEG in a single user message (no system message — Groq vision models do not accept system messages with image inputs).

**Prompt structure:**

```text
Read every line item and total from the receipt image.
Then apply the description for who ate what.
DESCRIPTION:
{description}
{full JSON schema block}
```

**Retry logic:**
- JSON failure → one retry (same as text path)
- After validation: if `"No line items"` or `"Grand total missing"` → third call with `CORRECTION REQUIRED: {issues}` appended

**What went wrong on vision path:**
- Model returned `Tender Coconut` in both `assignments["Nisha"]` and `shared` simultaneously → fixed with `_dedupe_exclusive_vs_shared()` (shared wins)
- Vision returned CGST and SGST as separate fields instead of combined GST → fixed with `bill_validation._consolidate_tax_fields()`
- Subtotal misreads on the text/OCR path (e.g. ₹1,110 vs ₹1,710) were mitigated with `_enrich_from_ocr()` — infers subtotal from service charge @10%, with a receipt-specific repair when grand total ≥ ₹1,900. The default vision path avoids most of that by reading the image directly; remaining total issues are caught by `validate_and_repair_bill()` and post-processing.

---

## Explicit answer: did the model do the arithmetic?

**No.**

The model (Groq Llama 4 Scout / Llama 3.3 70B) does structured extraction only:

- Reads the receipt and description
- Returns item names, amounts, who had what, who paid
- Makes language interpretations ("rest of us" → specific names)

All arithmetic is in `splitter.py` (pure Python):

- Proportional tax/service/discount allocation (`_allocate_proportional`)
- Per-unit rate calculation for fractional quantities
- Rounding with remainder absorbed by largest share
- Settle-up calculation
- Reconciliation check

**Reason:** LLMs hallucinate numbers under arithmetic pressure. Python division is exact. This separation also makes failures debuggable — OCR failures, LLM parsing failures, and arithmetic failures are distinct and logged separately.

---

# Where the AI Was Wrong — 3 Real Examples

## Example 1: False "item not found" flags

**Model did:** Emitted `flag_notes` like `"Butter Chicken mentioned in description not found on receipt"` when the item was clearly present in `items[]`.

**Correct answer:** Item exists on bill → assign it, no warning.

**Fixed by:** `_clean_false_flag_notes()` — after parsing, normalize item names and drop any "not found" flag where a fuzzy match exists in `items[]`. Also added `_supplement_assignments_from_description()` to fill assignments the model silently skipped.

---

## Example 2: Full line price charged to one person for fractional quantity

**Model did:** Description said "Aman had a Masala Coke" — bill line was `Masala Coke qty:2 ₹120`. Model put ₹120 in Aman's assignments.

**Correct answer:** 1× rate = ₹60. Remaining unit flagged as unassigned.

**Fixed by:** `splitter._food_amount_for_person()` now checks `_is_single_unit_mentioned()` and `_described_unit_count()`. If description says "a" or singular form, charge 1× `(amount/qty)`. Leftover units distributed via `_allocate_leftover_units()` with assumption note logged.

---

## Example 3: Empty shared dict blocking entire allocation

**Model did:** Returned `"shared": {"Butter Naan": [], "Jeera Rice": []}` — valid JSON, but no people listed. Splitter found no one to allocate to, food subtotal stayed ₹0 for everyone.

**Correct answer:** Items shared by all people in `all_people`.

**Fixed by:** `_strip_empty_shared()` removes shared entries with empty people lists before splitter runs. `_supplement_assignments_from_description()` then re-assigns common items using description patterns like "everything else was common to all", "we all had", and "for everyone".

---

## Tip handling (edge case 12)

Tip behavior spans three layers: prompt emits a `flag_note`, `_normalize_llm_inference_flags()` moves it out of user-facing flags into assumptions, and `calculate_split()` logs it as an assumption without adding rupees to totals. `EDGE_CASES.md` row 12 describes tip in assumptions; rupees are not added to per-person totals today. Known gap if tip must be split in cash.

---

*See `AI_FAILURES.md` for the same three examples in narrative form.*
