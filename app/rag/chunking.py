"""SmartChunker — copied from Sanshodhak paper-intel/rag/chunking.py."""
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import nltk

try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt", quiet=True)

try:
    nltk.data.find("tokenizers/punkt_tab")
except LookupError:
    nltk.download("punkt_tab", quiet=True)


@dataclass
class Chunk:
    text: str
    chunk_id: int
    doc_id: str
    start_char: int
    end_char: int
    metadata: Dict


class SmartChunker:
    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 128, use_semantic_split: bool = True):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.use_semantic_split = use_semantic_split

    def chunk_text(self, text: str, doc_id: str, metadata: Optional[Dict] = None) -> List[Chunk]:
        if not text.strip():
            return []
        metadata = metadata or {}
        if self.use_semantic_split:
            return self._semantic_chunk(text, doc_id, metadata)
        return self._simple_chunk(text, doc_id, metadata)

    def _semantic_chunk(self, text: str, doc_id: str, metadata: Dict) -> List[Chunk]:
        sentences = nltk.sent_tokenize(text)
        chunks, current_chunk, current_length = [], [], 0
        chunk_start, chunk_id = 0, 0
        for sentence in sentences:
            slen = len(sentence.split())
            if current_length + slen > self.chunk_size and current_chunk:
                chunk_text = " ".join(current_chunk)
                chunk_end = chunk_start + len(chunk_text)
                chunks.append(Chunk(chunk_text, chunk_id, doc_id, chunk_start, chunk_end, metadata))
                overlap_tokens, overlap_start = 0, len(current_chunk) - 1
                while overlap_start >= 0 and overlap_tokens < self.chunk_overlap:
                    overlap_tokens += len(current_chunk[overlap_start].split())
                    overlap_start -= 1
                overlap_start = max(0, overlap_start + 1)
                current_chunk = current_chunk[overlap_start:]
                current_length = sum(len(s.split()) for s in current_chunk)
                chunk_start = chunk_end - len(" ".join(current_chunk))
                chunk_id += 1
            current_chunk.append(sentence)
            current_length += slen
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append(Chunk(chunk_text, chunk_id, doc_id, chunk_start, chunk_start + len(chunk_text), metadata))
        return chunks

    def _simple_chunk(self, text: str, doc_id: str, metadata: Dict) -> List[Chunk]:
        words = text.split()
        chunks, start_idx, chunk_id = [], 0, 0
        while start_idx < len(words):
            end_idx = min(start_idx + self.chunk_size, len(words))
            chunk_text = " ".join(words[start_idx:end_idx])
            chunks.append(Chunk(chunk_text, chunk_id, doc_id,
                                sum(len(w) + 1 for w in words[:start_idx]),
                                sum(len(w) + 1 for w in words[:end_idx]), metadata))
            start_idx += self.chunk_size - self.chunk_overlap
            chunk_id += 1
        return chunks
