"""Branch 2 — anomaly detection (benign-only). STUB until the model is trained.

Owner: Bach. When the model lands, load it via the registry and fill
``anomaly_score`` / ``is_anomaly`` — the response shape already matches the
contract the frontend is built against.
"""

from __future__ import annotations

from fastapi import APIRouter

from deploy.schemas import Branch2Response, QueryRequest

router = APIRouter(prefix="/branch2", tags=["branch2"])


def run_branch2(query: str) -> Branch2Response:
    """Return the Branch-2 anomaly result (not_ready stub for now)."""
    return Branch2Response(
        status="not_ready",
        detail="Branch-2 anomaly model not trained yet.",
    )


@router.post("/score", response_model=Branch2Response)
def score(request: QueryRequest) -> Branch2Response:
    """Return a continuous anomaly score for a query (stub)."""
    return run_branch2(request.query)
