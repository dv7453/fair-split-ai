#!/usr/bin/env python3
"""Quick local check: health + one /split call. Run from backend/ with venv active."""

import base64
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "http://127.0.0.1:8001"
DESCRIPTION = (
    "Aman had Paneer Tikka, Butter Chicken, and a Masala Coke. "
    "Priya and Rohan shared Dal Makhani and Garlic Naan; they shared 2 Sweet Lassis. "
    "All three shared Jeera Rice. Priya paid."
)


def main() -> int:
    print("1. GET /health …")
    try:
        with urllib.request.urlopen(f"{API}/health", timeout=5) as resp:
            print("   ", resp.read().decode())
    except Exception as exc:
        print("   FAIL:", exc)
        print("   Start server: cd backend && source venv/bin/activate && uvicorn main:app --host 127.0.0.1 --port 8001 --reload")
        return 1

    img_path = _find_sample_receipt()
    if img_path is None:
        receipts = Path(__file__).resolve().parent / "test_data" / "receipts"
        print("2. No sample receipt image found — skip /split.")
        print(f"   Add images under: {receipts}")
        print("   or run: python smoke_test.py test_data/receipts/R1.jpg")
        return 0
    print(f"2. POST /split with {img_path.name} …")
    body = json.dumps(
        {
            "receipt_base64": base64.b64encode(img_path.read_bytes()).decode(),
            "description": DESCRIPTION,
        }
    ).encode()
    req = urllib.request.Request(
        f"{API}/split",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            print(f"   OK in {time.time() - t0:.1f}s — grand_total", data.get("grand_total"))
            for p in data.get("per_person", []):
                print(f"   {p['name']}: ₹{p['total']}")
            return 0
    except urllib.error.HTTPError as exc:
        print(f"   HTTP {exc.code} in {time.time() - t0:.1f}s:", exc.read().decode()[:500])
        return 1
    except Exception as exc:
        print(f"   FAIL in {time.time() - t0:.1f}s:", exc)
        return 1


def _find_sample_receipt() -> Path | None:
    if len(sys.argv) > 1:
        path = Path(sys.argv[1]).expanduser()
        return path if path.is_file() else None

    search_roots = [
        Path(__file__).resolve().parent / "test_data" / "receipts",
    ]
    patterns = (
        "receipt.*",
        "recipt*.*",
        "receipt*.png",
        "receipt*.jpg",
        "receipt*.jpeg",
    )
    for root in search_roots:
        if not root.is_dir():
            continue
        for pattern in patterns:
            matches = sorted(root.glob(pattern))
            if matches:
                return matches[0]
    return None


if __name__ == "__main__":
    sys.exit(main())
