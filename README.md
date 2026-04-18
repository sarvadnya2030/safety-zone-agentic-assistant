# Civilian Safety Zone Monitor — Agentic RAG Assistant

Real-time hazard intelligence assistant for the **Civilian Safety Zone Monitor** hackathon problem statement. Combines live open-data pulls, hybrid RAG, and an agentic LLM (NVIDIA NIM nemotron) to answer grounded safety questions about Indian disaster zones.

## Features

- **Live data pulls** — SACHET/NDMA alerts (CAP/RSS), IMD city weather warnings, NCS/USGS earthquakes, FSI forest fire hotspots (MODIS/VIIRS, 15-min updates), OSM relief infrastructure, ReliefWeb situation reports
- **Hybrid RAG** — BM25 + FAISS + RRF fusion over NDMA SOPs, hazard guidelines, and historical bulletins
- **Agentic loop** — NVIDIA NIM (nemotron) with 6 tools: `fetch_live_alerts`, `rag_search`, `find_relief_camps`, `get_district_risk`, `osm_area_profile`, `spatial_events`
- **Deterministic risk scoring** — district scores from India Flood Inventory (744 districts, Zenodo) + ISRO Landslide Atlas 2023 priors; LLM only explains, never invents scores
- **Grounded answers** — every factual claim must include `[source, timestamp]` citations

## Quick Start

```bash
git clone https://github.com/sarvadnya2030/safety-zone-agentic-assistant.git
cd safety-zone-agentic-assistant

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Set your NVIDIA API key
echo "NVIDIA_API_KEY=nvapi-..." > .env

# Seed docs + download India Flood Inventory
python scripts/bootstrap_docs.py

# Build FAISS + BM25 index
python scripts/build_index.py

# Start server
uvicorn app.main:app --reload --port 8090
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ask` | Main assistant — agentic RAG query |
| `GET` | `/events` | Structured event query (`?district=&since=`) |
| `GET` | `/camps` | Nearest relief camps (`?lat=&lon=&radius_km=`) |
| `GET` | `/insights/district/{name}` | Deterministic risk score (`?explain=true` for LLM explanation) |
| `GET` | `/infra` | OSM infrastructure profile (`?lat=&lon=&radius_m=`) |
| `GET` | `/health` | Health check |

## Demo Queries

```bash
# Earthquake activity near India
curl -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "What earthquake activity has happened near India in the last 24 hours?"}'

# District risk + active alerts
curl -X POST http://localhost:8090/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the current risk in Raigad district?", "district": "Raigad", "state": "Maharashtra"}'

# Relief camps near a point
curl "http://localhost:8090/camps?lat=18.52&lon=73.85&radius_km=20"

# OSM infrastructure profile
curl "http://localhost:8090/infra?lat=18.52&lon=73.85&radius_m=5000"

# District risk score
curl "http://localhost:8090/insights/district/Raigad?state=Maharashtra&explain=false"
```

## Data Sources

| Source | Type | URL |
|--------|------|-----|
| SACHET/NDMA | CAP/RSS alerts | https://sachet.ndma.gov.in/CapFeed |
| IMD | City weather warnings | https://city.imd.gov.in/citywx/responsive |
| NCS/USGS | Earthquakes | https://seismo.gov.in + USGS fallback |
| FSI | Forest fire hotspots (MODIS/VIIRS) | https://fsiforestfire.gov.in |
| OSM/Overpass | Relief infra, hospitals, shelters | https://overpass-api.de |
| ReliefWeb | Situation reports | https://api.reliefweb.int/v1/reports |
| India Flood Inventory | District flood severity (744 districts) | https://zenodo.org/doi/10.5281/zenodo.4742142 |
| ISRO Landslide Atlas | District landslide susceptibility | https://www.isro.gov.in/Landslide_Atlas_India.html |

## Stack

- **Backend**: FastAPI + uvicorn
- **LLM**: NVIDIA NIM — `nvidia/nemotron-3-nano-30b-a3b` (reasoning model)
- **Storage**: SQLite + FAISS + GeoJSON
- **Retrieval**: BM25 + FAISS with Reciprocal Rank Fusion
- **Embeddings**: `BAAI/bge-small-en-v1.5`

## Architecture

```
POST /ask
  └── agent/loop.py (ReAct, max 5 tool calls)
       ├── fetch_live_alerts  → pullers/{sachet,imd,ncs,fire}.py → SQLite events
       ├── rag_search         → app/rag/retrieval.py (BM25+FAISS+RRF)
       ├── find_relief_camps  → pullers/osm.py → SQLite camps
       ├── get_district_risk  → insights/scoring.py (deterministic)
       ├── osm_area_profile   → pullers/osm.py (11-category infra profile)
       └── spatial_events     → store/db.py (bbox+haversine query)
```
