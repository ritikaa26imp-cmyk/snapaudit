# SnapAudit

> AI-powered product swap detection for e-commerce supply chains.

SnapAudit compares two sets of product images — a catalog reference and an image of the product received or returned by the user — and returns a structured verdict on whether a product swap has occurred.

Built as an open-source portfolio project. Runs entirely on your local machine using open-source vision models. No external API calls, no per-request cost.

---

## The problem

Product swaps are a major source of loss in e-commerce:

**Return fraud** — A buyer receives a genuine product, initiates a return, and sends back a different or damaged item. The platform issues a refund. The seller loses both the product and the revenue.

**Delivery fraud** — A seller ships the wrong product, either deliberately or through a pick-and-pack error. The buyer receives something different from what was ordered.

Without automated image comparison, detecting swaps depends entirely on manual QC — slow, inconsistent, and unscalable at the volume of a large marketplace.

---

## What it does

- Compares two sets of product images (2–3 images per set)
- Runs a two-pass vision pipeline: visibility check → full comparison
- Evaluates four attributes independently: colour, design, category, quantity
- Returns a structured JSON verdict: match / mismatch / inconclusive
- Deterministic confidence scoring based on image quality signals
- Full audit log with filtering and CSV export
- Bulk comparison via CSV upload with row-by-row progress tracking
- Single-line model switching between Qwen2.5-VL, Gemma3, and LLaVA

---

## Model comparison

| Model | Size | Speed | Accuracy | Best for |
|---|---|---|---|---|
| qwen2.5vl:7b | 6.0 GB | ~45s / call | Best | Production use |
| gemma3:4b | 3.3 GB | ~20s / call | Good | Fast testing |
| llava:7b | 4.7 GB | ~40s / call | Baseline | Benchmarking |

Switch models by changing one line in `config.yaml`:
```yaml
active_model: "qwen2.5vl:7b"
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Vision models | Qwen2.5-VL, Gemma3, LLaVA via Ollama |
| Backend | FastAPI + Python 3.11 |
| Frontend | React + Vite |
| Database | SQLite via aiosqlite |
| Image processing | Pillow |
| Config and policies | PyYAML |

---

## Quick start

### Prerequisites
- Mac (Apple Silicon recommended) or Linux
- 16GB RAM recommended for qwen2.5vl:7b (8GB minimum for gemma3:4b)
- Ollama installed — https://ollama.com

### 1. Clone the repo
```bash
git clone https://github.com/ritikaa26imp-cmyk/snapaudit.git
cd snapaudit
```

### 2. Pull vision models
```bash
ollama pull qwen2.5vl:7b
ollama pull gemma3:4b
ollama pull llava:7b
```

### 3. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 4. Start the backend
```bash
python3.11 main.py
```
Backend runs on http://localhost:8000
Interactive API docs at http://localhost:8000/docs

### 5. Start the frontend
```bash
cd snapaudit/ui
npm install
npm run dev
```
Frontend runs on http://localhost:5173

---

## How it works
Request → Validate → Preprocess images → Pass 1 (visibility check)
→ Visibility rollup → Pass 2 (full comparison) → Confidence scoring
→ Audit log → Response

**Pass 1** checks whether the product is meaningfully visible in each image (visible / partial / not_visible). If a set fails the visibility rollup, the pipeline short-circuits and returns inconclusive without running Pass 2.

**Pass 2** compares colour, design, category, and quantity across both image sets using category-specific policy rules loaded from `policies/categories.yaml`. Policies are hot-reloaded — edit the file and changes take effect on the next request without restart.

**Confidence** is computed deterministically from four observable signals and is never self-reported by the model:

| Signal | Effect |
|---|---|
| Any partial image in either set | Minimum medium |
| Category was auto-detected | Minimum medium |
| 2+ attributes returned cant_say | Minimum medium |
| JSON retry triggered | Forces low |
| 3+ attributes returned cant_say | Forces low |
| None of the above | High |

---

## Supported categories

Sarees · Kurtis · Bags · Cloth items · Jewellery · Watches · Auto-detect

Each category has explicit match / mismatch / cant_say rules defined in `policies/categories.yaml`. Edit the file to tune sensitivity without a code deploy.

---

## API endpoints
POST /api/v1/compare          Run a comparison
GET  /api/v1/audits           List audit log with filters
GET  /api/v1/audits/{id}      Get a single audit record
GET  /api/v1/audits/export    Export filtered results as CSV
POST /api/v1/visibility       Single image visibility check
GET  /api/v1/health           Health check and active model name

---

## Project structure
snapaudit/
├── main.py                      FastAPI app entry point
├── config.yaml                  Model selection and all settings
├── policies/
│   └── categories.yaml          Match / mismatch rules per category
├── snapaudit/
│   ├── api/                     FastAPI routes and Pydantic schemas
│   ├── inference/               Ollama client, Pass 1, Pass 2, prompt builder
│   ├── pipeline/                Validator, preprocessor, rollup, confidence, orchestrator
│   └── audit/                   SQLite audit log
└── snapaudit/ui/                React + Vite frontend (5 screens)

---

## Screens

| Screen | Route | Description |
|---|---|---|
| Compare | / | Upload images, run comparison, view verdict |
| Bulk | /bulk | Upload CSV, process multiple rows, download results |
| Audit log | /audits | Filter and export all past comparisons |
| Visibility check | /visibility | Test a single image for visibility score |
| Policy viewer | /policy | Read-only view of all category rules |

---

## Future enhancements

- Backend queue (Celery + Redis) for large-scale batch processing
- Authentication and multi-user support
- Video frame extraction and comparison
- Webhook triggers for automated pipeline integration
- Fine-tuned model for Indian fashion sub-categories
