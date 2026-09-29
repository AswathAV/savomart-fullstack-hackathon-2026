# Savo SiteScout: Chennai expansion intelligence platform

From "which area?" to "which property?" to "is the catchment right?" for four personas (BD Manager, BD Executive, Survey Manager, Survey Executive).
Stack: **FastAPI + SQLAlchemy (SQLite)** · **React + Vite + Leaflet/OpenStreetMap**. Brand colours `#782B90` / `#FFF200`.

## Run locally
```bash
# 1. Backend (Python 3.10+)
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # optional: LLM key, stores token
python seed.py                                         # demo data (offline, labelled simulated)
uvicorn app.main:app --reload --port 8000

# 2. Frontend (Node 18+), new terminal
cd frontend && npm install && npm run dev              # http://localhost:5173
```
Tests: `cd backend && python -m pytest -q`. Load `.env` yourself (`export $(grep -v '^#' .env | xargs)`) or set variables in the shell.

## Demo users (role switcher, top right)
1 Priya = BD Manager · 2 Karthik, 3 Meena = BD Executive · 4 Arun = Survey Manager · 5 Divya, 6 Ravi = Survey Executive. No passwords by design; the API enforces roles via `X-User-Id`.

**Demo path:** Priya → Areas → search `Velachery` → Run analysis → open report → tap hotspot → send to Karthik → Karthik: Scout → Add property (uses GPS/map) → Priya: Pipeline → property → Request study → Arun: Split + Assign → Divya/Ravi: capture lanes, Submit → property re-evaluates automatically.

## Architecture
React SPA → REST (`/api`) → FastAPI → SQLite. Long jobs (area analysis, property evaluation) run as background tasks with progress polling (`pending → running → done | failed`, retryable). External data: Overpass (OSM) and the Savomart stores API, both cached and wrapped with provenance metadata.

## Data model (`backend/app/core.py`)
`users` · `reports` (cells, status/progress, result JSON with factors, hotspots, narrative, provenance) · `properties` (pin, details JSON, photos, stage, evaluation JSON) · `events` (audit trail + activity feed) · `directives` (manager → executive hotspot) · `surveys` (request, 250 m cell plan, rollup) · `tasks` (one 250 m cell each, lane data, `reused_from`).
Spatial approach: a **fixed global grid** (500 m for areas, 250 m for surveys, every 500 m cell splits exactly into four 250 m cells). Cell ids like `250:5301:8422` make selection, aggregation, non-overlapping splits and reuse plain indexed lookups. For production, move to Postgres + PostGIS.

## Data sources
OpenStreetMap via Overpass (shops, schools, clinics, offices, transit, residential buildings) · Savomart stores API · Nominatim/OSRM/Census/pincode boundaries are *not* used yet.
**Mock, labelled in UI and reports:** locality centroids, population density, income index and rent benchmark (`geo.py`, hand-estimated for 18 localities; replace with Census ward data and broker rents). If Overpass or the stores API is unreachable, clearly flagged **simulated/sample** data is used so the workflow never dead-ends.

## Workflow decisions
- Pipeline: scouted → shortlisted → study requested → under review → approved / rejected; manager-only moves, mandatory reason, full history.






