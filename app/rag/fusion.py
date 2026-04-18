"""RRF fusion — copied verbatim from Sanshodhak paper-intel/core/fusion.py."""
from typing import Dict, List, Optional, Tuple


def reciprocal_rank_fusion(
    ranked_lists: List[List[Tuple[str, float]]],
    weights: Optional[List[float]] = None,
    k: int = 60,
) -> List[Tuple[str, float]]:
    if weights is None:
        weights = [1.0] * len(ranked_lists)
    if len(weights) != len(ranked_lists):
        raise ValueError("weights must have the same length as ranked_lists")
    scores: Dict[str, float] = {}
    for ranked, w in zip(ranked_lists, weights):
        for rank, (doc_id, _) in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + w / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
