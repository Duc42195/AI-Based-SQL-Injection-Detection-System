"""Branch 1 — supervised multiclass SQLi classifier (trained: tfidf_logreg)."""

from __future__ import annotations

from fastapi import APIRouter

from deploy.registry import get_registry
from deploy.schemas import Nhanh1Response, QueryRequest

router = APIRouter(prefix="/nhanh1", tags=["nhanh1"])


def run_nhanh1(query: str) -> Nhanh1Response:
    """Run Branch-1 inference, or a structured not_ready response if unloaded.

    Shared by this router and the unified ``/detect`` endpoint so both return
    the exact same shape.
    """
    model = get_registry().nhanh1()
    if model is None:
        return Nhanh1Response(
            status="not_ready",
            detail="Branch-1 model not loaded (missing weights under models/).",
        )
    pred = model.predict(query)
    return Nhanh1Response(
        status="ready",
        query_canonical=pred.query_canonical,
        label=pred.label,
        label_name=pred.label_name,
        is_sqli=pred.is_sqli,
        confidence=pred.confidence,
        attack_probability=pred.attack_probability,
        probabilities=pred.probabilities,
        threshold=pred.threshold,
    )


@router.post("/predict", response_model=Nhanh1Response)
def predict(request: QueryRequest) -> Nhanh1Response:
    """Classify a single query into Normal or a specific SQLi attack class."""
    return run_nhanh1(request.query)
