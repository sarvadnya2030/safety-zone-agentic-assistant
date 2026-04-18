#!/usr/bin/env python3
"""Build FAISS + BM25 index from data/docs/."""
import sys
from pathlib import Path

# Allow running as script from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import cfg
from app.rag.ingest import build_index

if __name__ == "__main__":
    docs_dir = cfg("data.docs_dir", "data/docs")
    index_dir = cfg("data.index_dir", "data/index")
    print(f"Building index from {docs_dir} -> {index_dir}")
    n = build_index(docs_dir, index_dir)
    print(f"Done. {n} chunks indexed.")
