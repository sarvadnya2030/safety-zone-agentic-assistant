"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import cfg
from app.store.db import init_db
from app.rag.ingest import load_index
from app.routers import ask, events, camps, insights, infra

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    db_path = cfg("data.db_path", "data/events.db")
    index_dir = cfg("data.index_dir", "data/index")

    logger.info("Initialising DB at %s", db_path)
    init_db(db_path)

    logger.info("Loading RAG index from %s", index_dir)
    ok = load_index(index_dir)
    if not ok:
        logger.warning("RAG index not found — /ask will work but rag_search will return an error. Run scripts/build_index.py to fix.")

    logger.info("Civilian Safety Monitor ready")
    yield
    # Shutdown (nothing to clean up for SQLite)


app = FastAPI(
    title="Civilian Safety Zone Monitor",
    description="Agentic hazard intelligence assistant with live data + RAG",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ask.router)
app.include_router(events.router)
app.include_router(camps.router)
app.include_router(insights.router)
app.include_router(infra.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
