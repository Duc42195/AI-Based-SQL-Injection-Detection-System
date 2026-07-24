"""Branch 2 — anomaly detection (benign-only). STUB until the model is trained.

Owner: Bach. When the model lands, load it via the registry and fill
``anomaly_score`` / ``is_anomaly`` — the response shape already matches the
contract the frontend is built against.
"""

from __future__ import annotations

from fastapi import APIRouter

from deploy.schemas import Nhanh2Response, QueryRequest

router = APIRouter(prefix="/nhanh2", tags=["nhanh2"])


def run_nhanh2(query: str) -> Nhanh2Response:
    """Return the Branch-2 anomaly result (not_ready stub for now)."""
    return Nhanh2Response(
        status="not_ready",
        detail="Branch-2 anomaly model not trained yet.",
    )


@router.post("/score", response_model=Nhanh2Response)
def score(request: QueryRequest) -> Nhanh2Response:
    """Return a continuous anomaly score for a query (stub)."""
    return run_nhanh2(request.query)
