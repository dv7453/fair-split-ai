# Edge Cases

| # | Edge Case | Input Example | How Handled | Verified? |
|---|-----------|--------------|-------------|-----------|
| 1 | No service charge on bill | service_charge line absent | `service_charge=0`, no flag | Yes |
| 2 | Printed total doesn't add up | subtotal+tax+service ≠ grand_total | Flag with exact difference | Yes |
| 3 | Item in description not on bill | "Aman had the cheesecake" — no cheesecake on receipt | Flag it, skip in calculation | Yes |
| 4 | "rest of us" in description | "rest of us shared the naan" | Interpret as all_people minus exclusively-assigned, add assumption | Yes |
| 5 | Subset sharing (not all people) | "Gulab Jamun shared by Priya and Karan only" | Split amount only between named sharers | Yes |
| 6 | Quantities don't divide evenly | 3 people share ₹100 item | Split as 34/33/33, largest-share absorbs remainder, note in assumptions | Yes |
| 7 | No payer stated | description has no "X paid" | `paid_by=null`, flag it, `settle_up=[]` | Yes |
| 8 | Person with no items | "Aman was there but only had water (not on bill)" | subtotal=0, included in headcount, flagged | Yes |
| 9 | Discount larger than subtotal | discount=15%, printed total goes negative | Flag "Discount exceeds subtotal" | Yes |
| 10 | Bill grand total unreadable | OCR confidence < 0.7 on total | Wiring exists (`_low_confidence_flags` → `flags[]`) but `low_confidence_cells` is always `[]` in current OCR engine — flag never fires in practice | No |
| 11 | Multiple quantities of same item | "Butter Naan 4 — ₹240" | Split the ₹240 total, not ₹60/each, unless description specifies per-person qty | Yes |
| 12 | Tip in description | "We left a ₹200 tip" | Logged in `assumptions` only; not added to per-person totals unless on receipt | Partial |
| 13 | Same person pays for others who aren't there | only one person in group | `settle_up=[]`, no one owes | Yes |
| 14 | Corrupted/blurry image | OCR returns empty or gibberish | 400 error with clear message | Yes |
| 15 | No table structure on receipt | photo of handwritten note | OCR uses `raw_lines`; API flag "No table structure detected — results may be less accurate" | Yes |
| 16 | Empty request body fields | missing `receipt_base64` or `description` | 400 `{"error": "...", "flags": []}` | Yes |
| 17 | Invalid base64 / corrupt image bytes | truncated or non-image file | 400 preprocess error with message | Yes |
| 18 | No items assigned to anyone | empty `assignments` and `shared` | Flag + `ValueError` "No items assigned to anyone" → 500 | Yes |
| 19 | LLM returns invalid JSON | malformed or fenced JSON twice | Retry once; 500 `LLM parsing failed` with raw response in `flags` | Yes |
| 20 | Missing `GROQ_API_KEY` | `.env` placeholder | `ValueError` on parse → 500 | Yes |
| 21 | OCR price column O/I confusion | amount reads `I8O` | Not implemented — `ocr_engine.py` does currency normalization only; no O→0 / I→1 substitution; `corrections` always `[]` | No |
| 22 | Currency symbols mixed | ₹, Rs., INR on same receipt | Normalized to `INR ` in OCR pipeline | Yes |
| 23 | Single payer, multiple diners | "Priya paid for everyone" | `settle_up`: each non-payer → payer for their `total` | Yes |
| 24 | Reconciliation mismatch after rounding | person totals ≠ `grand_total` | Red banner in UI; flag with ₹ difference | Yes |
| 25 | Cold start / first deploy | Render free tier idle | ~30s wake on free tier | Yes |
| 26 | "a Masala Coke" (qty 2 on bill) | one coke in description | Charge 1× rate (₹60), flag extra unit on bill | Yes |
| 27 | "2 Sweet Lassis" (qty 3 on bill) | two lassis shared | 2× rate split between sharers; flag 3rd lassi | Yes |
| 28 | Two people, one line qty 2 | Dev & Nikhil each chicken biryani | 1× rate per person | Yes |
| 29 | Vision default (`USE_VISION=1`) | receipt photo | Groq reads image; no Tesseract | Yes |
| 30 | ±₹1 grand total mismatch | rounding | Absorbed on largest share; noted in assumptions | Yes |

## Automated regression tests

Run anytime (no server, no API key):

```bash
cd backend && source venv/bin/activate
python run_all_tests.py
```

Covers assignment bills R1–R4, Spice Route fractions, scenario bills, and edge cases in `backend/tests/`.

## Notes from testing

- **Row 6:** Remainder adjustment applies to proportional **discount / service / GST**, not food splits (food uses float division until final `round()`).
- **Row 10:** Infrastructure for low-confidence flagging exists in `main.py` (`_low_confidence_flags` → `result["flags"]`) but `ocr_engine.py` always returns `low_confidence_cells: []` — the wiring is unused. Same for Row 21.
- **Row 12:** Tip is noted in `assumptions`; rupee split not implemented yet (see `PROMPT_LOG.md`).
