"""Smoke tests for HybridRetriever."""
import tempfile
from pathlib import Path


def test_hybrid_retriever_build_and_search():
    from app.rag.retrieval import EmbeddingBackend, BM25Retriever, DenseRetriever, HybridRetriever

    docs = [
        ("d1", "Maharashtra flood warning red alert heavy rainfall"),
        ("d2", "Earthquake tremor 4.2 magnitude Uttarakhand seismic"),
        ("d3", "Relief camp shelter hospital water point Pune district"),
        ("d4", "Cyclone landfall Bay of Bengal Odisha coast storm surge"),
    ]
    ids = [d[0] for d in docs]
    texts = [d[1] for d in docs]

    backend = EmbeddingBackend()
    bm25 = BM25Retriever().build(ids, texts)
    dense = DenseRetriever(backend).build(ids, texts)
    hybrid = HybridRetriever(dense, bm25)

    results = hybrid.retrieve("flood Maharashtra", top_k=2)
    assert len(results) > 0
    assert results[0][0] == "d1", f"Expected d1 top, got {results[0][0]}"


def test_bm25_save_load():
    from app.rag.retrieval import BM25Retriever
    with tempfile.TemporaryDirectory() as tmpdir:
        path = str(Path(tmpdir) / "bm25.pkl")
        bm25 = BM25Retriever().build(["a", "b"], ["flood warning", "earthquake alert"])
        bm25.save(path)
        loaded = BM25Retriever().load(path)
        r = loaded.retrieve("flood", top_k=1)
        assert r[0][0] == "a"


def test_smart_chunker():
    from app.rag.chunking import SmartChunker
    # 100 sentences of ~10 words each → should produce multiple chunks at chunk_size=30
    text = " ".join(f"Sentence {i} has hazard flood warning alert district." for i in range(100))
    chunker = SmartChunker(chunk_size=30, chunk_overlap=5)
    chunks = chunker.chunk_text(text, "doc1")
    assert len(chunks) > 1
    assert all(c.doc_id == "doc1" for c in chunks)
