import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("fair-split")

_backend_dir = Path(__file__).resolve().parent
_repo_root = _backend_dir.parent
_frontend_dir = _repo_root / "frontend"
_test_receipts_dir = _backend_dir / "test_data" / "receipts"
_test_cases_path = _backend_dir / "test_data" / "test_cases.json"
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ocr_engine import create_ocr_engine, run_ocr
from parser import VISION_MODEL, parse_bill, parse_bill_from_image
from preprocessor import preprocess_image
from splitter import calculate_split
from validate import validate_split_response

load_dotenv(Path(__file__).parent / ".env")

app = FastAPI(title="fair-split")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LLM_MODEL = "groq/llama-3.3-70b-versatile"
USE_VISION = os.getenv("USE_VISION", "1").lower() in ("1", "true", "yes")
NO_TABLE_FLAG = (
    "No table structure detected — results may be less accurate"
)


class SplitRequest(BaseModel):
    receipt_base64: str = Field(..., description="Base64-encoded receipt image")
    description: str = Field(..., description="Who ate what, in plain English")


@app.on_event("startup")
async def startup_event() -> None:
    if USE_VISION:
        app.state.ocr_engine = None
        logger.info("Using vision model %s (set USE_VISION=0 for Tesseract)", VISION_MODEL)
    else:
        app.state.ocr_engine = create_ocr_engine()


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "ocr": "vision" if USE_VISION else "tesseract",
        "llm": VISION_MODEL if USE_VISION else LLM_MODEL,
    }


@app.get("/test-cases")
def list_test_cases() -> JSONResponse:
    """Metadata for E2E test receipts (image filename + description)."""
    if not _test_cases_path.is_file():
        raise HTTPException(status_code=404, detail="test_cases.json not found")
    with _test_cases_path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return JSONResponse(content=payload)


@app.get("/")
def serve_frontend() -> FileResponse:
    """Serve UI over http://127.0.0.1:8001/ (avoids file:// CORS blocks)."""
    index = _frontend_dir / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="frontend/index.html not found")
    return FileResponse(index)


@app.post("/split")
def split_receipt(body: SplitRequest, request: Request) -> JSONResponse:
    """Sync route — runs in a thread pool so OCR/LLM don't block other requests."""
    receipt_base64 = body.receipt_base64.strip()
    description = body.description.strip()

    if not receipt_base64 or not description:
        return JSONResponse(
            status_code=400,
            content={
                "error": "receipt_base64 and description are required and must be non-empty",
                "flags": [],
            },
        )

    try:
        logger.info("split: preprocessing image")
        image, _preprocess_meta = preprocess_image(receipt_base64)
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={
                "error": f"Failed to preprocess receipt image: {exc}",
                "flags": [],
            },
        )

    try:
        if USE_VISION:
            logger.info("split: vision parse (image + description)")
            parsed = parse_bill_from_image(image, description)
            ocr_result = {
                "table_found": True,
                "corrections": [],
                "low_confidence_cells": [],
            }
        else:
            ocr_engine = request.app.state.ocr_engine
            logger.info("split: running OCR")
            ocr_result = run_ocr(image, ocr_engine)
            logger.info("split: calling LLM parser")
            parsed = parse_bill(ocr_result, description)
    except RuntimeError as exc:
        return JSONResponse(
            status_code=400,
            content={"error": str(exc), "flags": []},
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=500,
            content={
                "error": "LLM parsing failed",
                "flags": _extract_llm_raw_response(exc),
            },
        )

    try:
        result = calculate_split(parsed)
    except ValueError as exc:
        content: dict = {"error": str(exc), "flags": list(parsed.get("flag_notes") or [])}
        if "No items assigned" in str(exc):
            content["items_on_bill"] = [
                item.get("name") for item in (parsed.get("items") or [])
            ]
            content["assignments"] = parsed.get("assignments") or {}
            content["shared"] = parsed.get("shared") or {}
            content["all_people"] = parsed.get("all_people") or []
        return JSONResponse(status_code=400, content=content)

    result["assumptions"] = list(result.get("assumptions") or [])
    result["assumptions"].extend(ocr_result.get("corrections") or [])

    result["flags"] = list(result.get("flags") or [])
    result["flags"].extend(_low_confidence_flags(ocr_result.get("low_confidence_cells") or []))

    if not ocr_result.get("table_found"):
        result["flags"].append(NO_TABLE_FLAG)

    schema_errors = validate_split_response(result)
    if schema_errors:
        return JSONResponse(
            status_code=500,
            content={"error": "Invalid response shape", "flags": schema_errors},
        )

    logger.info("split: done")
    return JSONResponse(status_code=200, content=result)


if _frontend_dir.is_dir():
    app.mount(
        "/static",
        StaticFiles(directory=str(_frontend_dir)),
        name="frontend-static",
    )

if _test_receipts_dir.is_dir():
    app.mount(
        "/test-receipts",
        StaticFiles(directory=str(_test_receipts_dir)),
        name="test-receipts",
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "flags": []},
    )


def _extract_llm_raw_response(exc: ValueError) -> list[str]:
    message = str(exc)
    marker = "Raw response:\n"
    if marker in message:
        return [message.split(marker, 1)[1]]
    return [message]


def _low_confidence_flags(cells: list[dict]) -> list[str]:
    flags: list[str] = []
    for cell in cells:
        text = cell.get("text", "")
        confidence = cell.get("confidence", 0)
        position = cell.get("position", "unknown")
        flags.append(
            f'Low confidence OCR: "{text}" ({confidence:.2f} at {position})'
        )
    return flags
