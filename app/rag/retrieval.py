"""
Dense (FAISS) and Sparse (BM25) retrieval.
Adapted from Sanshodhak paper-intel/core/retrieval.py — uses bge-small-en-v1.5 for speed.
"""
import json
import logging
import math
import pickle
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingBackend:
    def __init__(self, st_model: str = "BAAI/bge-small-en-v1.5", dim: int = 384) -> None:
        self.dim = dim
        self._model = None
        try:
            from sentence_transformers import SentenceTransformer
            m = SentenceTransformer(st_model, device="cpu")
            probe = m.encode(["probe"], show_progress_bar=False)
            self.dim = probe.shape[1]
            self._model = m
            logger.info("EmbeddingBackend: %s dim=%d", st_model, self.dim)
        except Exception as exc:
            logger.error("EmbeddingBackend init failed: %s", exc)

    def encode(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        if self._model is None:
            return np.zeros((len(texts), self.dim), dtype=np.float32)
        vecs = self._model.encode(
            texts, batch_size=batch_size, show_progress_bar=False, normalize_embeddings=True
        )
        return np.asarray(vecs, dtype=np.float32)


class BM25Retriever:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._doc_ids: List[str] = []
        self._tf: List[Dict[str, int]] = []
        self._df: Dict[str, int] = defaultdict(int)
        self._avgdl: float = 1.0
        self._N: int = 0

    @staticmethod
    def tokenise(text: str) -> List[str]:
        return text.lower().split()

    def build(self, doc_ids: List[str], texts: List[str]) -> "BM25Retriever":
        self._doc_ids = list(doc_ids)
        self._N = len(texts)
        self._tf = []
        self._df = defaultdict(int)
        total_len = 0
        for text in texts:
            tokens = self.tokenise(text)
            total_len += len(tokens)
            tf: Dict[str, int] = defaultdict(int)
            for t in tokens:
                tf[t] += 1
            self._tf.append(dict(tf))
            for t in set(tf):
                self._df[t] += 1
        self._avgdl = total_len / self._N if self._N > 0 else 1.0
        return self

    def score(self, query_tokens: List[str], doc_idx: int) -> float:
        tf = self._tf[doc_idx]
        dl = sum(tf.values())
        score = 0.0
        for t in query_tokens:
            if t not in tf:
                continue
            df_t = self._df.get(t, 0)
            idf = math.log((self._N - df_t + 0.5) / (df_t + 0.5) + 1.0)
            tf_norm = (tf[t] * (self.k1 + 1)) / (
                tf[t] + self.k1 * (1 - self.b + self.b * dl / self._avgdl)
            )
            score += idf * tf_norm
        return score

    def retrieve(self, query: str, top_k: int = 100) -> List[Tuple[str, float]]:
        tokens = self.tokenise(query)
        scored = [(self._doc_ids[i], self.score(tokens, i)) for i in range(self._N)]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def save(self, path: str) -> None:
        with open(path, "wb") as fh:
            pickle.dump({"doc_ids": self._doc_ids, "tf": self._tf,
                         "df": dict(self._df), "avgdl": self._avgdl,
                         "N": self._N, "k1": self.k1, "b": self.b}, fh)

    def load(self, path: str) -> "BM25Retriever":
        with open(path, "rb") as fh:
            d = pickle.load(fh)
        self._doc_ids = d["doc_ids"]
        self._tf = d["tf"]
        self._df = defaultdict(int, d["df"])
        self._avgdl = d["avgdl"]
        self._N = d["N"]
        self.k1 = d["k1"]
        self.b = d["b"]
        return self


class DenseRetriever:
    def __init__(self, backend: EmbeddingBackend) -> None:
        self.backend = backend
        self._index = None
        self._doc_ids: List[str] = []

    def build(self, doc_ids: List[str], texts: List[str], batch_size: int = 32) -> "DenseRetriever":
        import faiss
        self._doc_ids = list(doc_ids)
        vecs = self.backend.encode([t[:2048] for t in texts], batch_size=batch_size)
        self._index = faiss.IndexFlatIP(vecs.shape[1])
        self._index.add(vecs)
        logger.info("DenseRetriever: built %d vectors dim=%d", self._index.ntotal, vecs.shape[1])
        return self

    def retrieve(self, query: str, top_k: int = 100) -> List[Tuple[str, float]]:
        q_vec = self.backend.encode([query])
        k = min(top_k, len(self._doc_ids))
        scores, indices = self._index.search(q_vec, k)
        return [(self._doc_ids[int(i)], float(s)) for s, i in zip(scores[0], indices[0]) if i >= 0]

    def save(self, index_path: str, meta_path: str) -> None:
        import faiss
        faiss.write_index(self._index, index_path)
        with open(meta_path, "w") as fh:
            json.dump(self._doc_ids, fh)

    def load(self, index_path: str, meta_path: str) -> "DenseRetriever":
        import faiss
        self._index = faiss.read_index(index_path)
        with open(meta_path) as fh:
            self._doc_ids = json.load(fh)
        return self


class HybridRetriever:
    def __init__(self, dense: DenseRetriever, bm25: BM25Retriever) -> None:
        self.dense = dense
        self.bm25 = bm25

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        dense_weight: float = 1.0,
        bm25_weight: float = 1.0,
        rrf_k: int = 60,
    ) -> List[Tuple[str, float]]:
        from app.rag.fusion import reciprocal_rank_fusion
        fetch_k = max(top_k * 2, 100)
        dense_res = self.dense.retrieve(query, top_k=fetch_k)
        bm25_res = self.bm25.retrieve(query, top_k=fetch_k)
        fused = reciprocal_rank_fusion(
            [dense_res, bm25_res], weights=[dense_weight, bm25_weight], k=rrf_k
        )
        return fused[:top_k]
