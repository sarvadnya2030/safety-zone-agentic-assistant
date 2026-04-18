"""Build FAISS + BM25 index from data/docs/."""
import json
import logging
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.rag.chunking import SmartChunker, Chunk
from app.rag.retrieval import EmbeddingBackend, BM25Retriever, DenseRetriever
from app.config import cfg

logger = logging.getLogger(__name__)

_chunker: Optional[SmartChunker] = None
_backend: Optional[EmbeddingBackend] = None
_bm25: Optional[BM25Retriever] = None
_dense: Optional[DenseRetriever] = None
_chunk_meta: Dict[str, Dict] = {}  # chunk_id -> {text, source, title, published_at, url}


def get_hybrid_retriever():
    """Return a HybridRetriever if index is loaded, else None."""
    if _bm25 is None or _dense is None:
        return None
    from app.rag.retrieval import HybridRetriever
    return HybridRetriever(_dense, _bm25)


def get_chunk_meta(chunk_id: str) -> Dict:
    return _chunk_meta.get(chunk_id, {})


def load_index(index_dir: str) -> bool:
    global _bm25, _dense, _backend, _chunk_meta
    idx = Path(index_dir)
    required = [idx / "faiss.index", idx / "faiss_meta.json",
                idx / "bm25.pkl", idx / "chunk_meta.json"]
    if not all(p.exists() for p in required):
        logger.warning("Index not found at %s — run scripts/build_index.py first", index_dir)
        return False
    embed_model = cfg("retrieval.embed_model", "BAAI/bge-small-en-v1.5")
    _backend = EmbeddingBackend(st_model=embed_model)
    _dense = DenseRetriever(_backend).load(
        str(idx / "faiss.index"), str(idx / "faiss_meta.json")
    )
    _bm25 = BM25Retriever().load(str(idx / "bm25.pkl"))
    with open(idx / "chunk_meta.json") as f:
        _chunk_meta = json.load(f)
    logger.info("RAG index loaded: %d chunks", len(_chunk_meta))
    return True


def build_index(docs_dir: str, index_dir: str) -> int:
    global _bm25, _dense, _backend, _chunk_meta
    docs = Path(docs_dir)
    idx = Path(index_dir)
    idx.mkdir(parents=True, exist_ok=True)

    embed_model = cfg("retrieval.embed_model", "BAAI/bge-small-en-v1.5")
    chunk_size = cfg("retrieval.chunk_size", 512)
    chunk_overlap = cfg("retrieval.chunk_overlap", 128)

    _backend = EmbeddingBackend(st_model=embed_model)
    chunker = SmartChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    all_ids: List[str] = []
    all_texts: List[str] = []
    meta: Dict[str, Dict] = {}

    for doc_path in sorted(docs.glob("**/*.txt")) + sorted(docs.glob("**/*.md")):
        doc_id = doc_path.stem
        text = doc_path.read_text(encoding="utf-8", errors="ignore")
        doc_meta = _read_meta(doc_path)
        chunks = chunker.chunk_text(text, doc_id, doc_meta)
        for chunk in chunks:
            cid = f"{doc_id}::{chunk.chunk_id}"
            all_ids.append(cid)
            all_texts.append(chunk.text)
            meta[cid] = {"text": chunk.text, **doc_meta}

    if not all_ids:
        logger.warning("No documents found in %s", docs_dir)
        return 0

    bm25 = BM25Retriever().build(all_ids, all_texts)
    bm25.save(str(idx / "bm25.pkl"))

    dense = DenseRetriever(_backend).build(all_ids, all_texts)
    dense.save(str(idx / "faiss.index"), str(idx / "faiss_meta.json"))

    with open(idx / "chunk_meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    _bm25, _dense, _chunk_meta = bm25, dense, meta
    logger.info("Index built: %d chunks", len(all_ids))
    return len(all_ids)


def _read_meta(doc_path: Path) -> Dict:
    meta_path = doc_path.with_suffix(".meta.json")
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text())
        except Exception:
            pass
    return {"source": doc_path.parent.name, "title": doc_path.stem, "url": ""}
