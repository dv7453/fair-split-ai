# Fair-split-ai

Split bills fairly from receipt photos: vision/OCR reads the receipt, Groq parses who ate what, **Python** (`splitter.py`) does all arithmetic.

## Structure

- `backend/` — FastAPI API, parser, splitter, tests
- `frontend/index.html` — UI (served at `/` when the API runs)
- `backend/test_data/` — receipt images + `test_cases.json` for the UI test panel

## Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create `backend/.env` with `GROQ_API_KEY=your_key`.

## Run locally

```bash
cd backend && source venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

Open **http://127.0.0.1:8001/** (not `file://`).

Default: **vision** (`USE_VISION=1`, Groq reads the image). OCR fallback: `USE_VISION=0`.

## API

`POST /split` — JSON body:

```json
{
  "receipt_base64": "<base64, no data: prefix>",
  "description": "<who ate what; who paid>"
}
```

## Tests

Offline (no server, no API key):

```bash
cd backend && source venv/bin/activate
python run_all_tests.py
```

Live smoke (server must be running on port 8001):

```bash
python smoke_test.py
python smoke_test.py test_data/receipts/R1.jpg
```

## Deploy (Render)

**Dashboard settings** (must match):

| Field | Value |
|-------|--------|
| Root Directory | *(empty)* |
| Build Command | `pip install -r backend/requirements-deploy.txt` |
| Start Command | `bash start.sh` |
| `PYTHON_VERSION` | `3.11.9` |
| `GROQ_API_KEY` | your Groq key |
| `USE_VISION` | `1` |

1. Connect [dv7453/fair-split-ai](https://github.com/dv7453/fair-split-ai) on [render.com](https://render.com).
2. Add the environment variables above (Render ignores `runtime.txt` unless `PYTHON_VERSION` is set).
3. Open `https://<your-service>.onrender.com/` — UI is served from the API root.

Health check: `GET /health`

Free tier may cold-start (~30s). For a separate static host, set `window.API_BASE` in `frontend/index.html` to your Render URL.

## Submission docs

| File | Purpose |
|------|---------|
| `PROMPT_LOG.md` | Prompt iterations |
| `EDGE_CASES.md` | Edge cases + how handled |
| `AI_FAILURES.md` | Three real AI failure examples |

Assignment bills: `backend/test_data/receipts/R1.jpg`–`R4.jpg` with descriptions in `test_cases.json`.
