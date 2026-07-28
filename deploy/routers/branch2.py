"""Branch 2 — anomaly detection (benign-only One-Class SVM).

Serves the trained model via the registry: canonicalize -> statistical features
-> anomaly score. Falls back to a structured ``not_ready`` response if the
weights are missing, so the API shape stays stable.
"""

from __future__ import annotations

from fastapi import APIRouter

from deploy.registry import get_registry
from deploy.schemas import Branch2Response, QueryRequest

router = APIRouter(prefix="/branch2", tags=["branch2"])


def run_branch2(query: str) -> Branch2Response:
    """Run Branch-2 inference, or a structured not_ready response if unloaded."""
    model = get_registry().branch2()
    if model is None:
        return Branch2Response(
            status="not_ready",
            detail="Branch-2 model not loaded (missing weights under models/).",
        )
    pred = model.predict(query)
    return Branch2Response(
        status="ready",
        query_canonical=pred.query_canonical,
        anomaly_score=pred.anomaly_score,
        is_anomaly=pred.is_anomaly,
    )


@router.post("/score", response_model=Branch2Response)
def score(request: QueryRequest) -> Branch2Response:
    """Return a continuous anomaly score + flag for a query."""
    return run_branch2(request.query)
