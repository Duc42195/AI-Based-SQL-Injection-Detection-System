"""Branch 3 — session-level sequence model.

Classifies a session from per-step Branch 1 + Branch 2 scores via a GRU.
Returns ``not_ready`` if the weights aren't found under ``models/branch3_v1/``.
The response shape matches the frontend contract regardless of readiness.
"""

from __future__ import annotations

from fastapi import APIRouter

from deploy.registry import get_registry
from deploy.schemas import Branch3Response, SessionRequest

router = APIRouter(prefix="/branch3", tags=["branch3"])


def run_branch3(queries: list[str]) -> Branch3Response:
    """Run Branch-3 inference, or a structured not_ready response if unloaded."""
    reg = get_registry()
    model = reg.branch3()
    if model is None:
        return Branch3Response(
            status="not_ready",
            detail="Branch-3 model not loaded (missing weights under models/branch3_v1/).",
        )
    b1 = reg.branch1()
    b2 = reg.branch2()
    pred = model.predict(queries, b1, b2)
    return Branch3Response(
        status="ready",
        session_label=pred.session_label,
        is_attack=pred.is_attack,
        detail=None,
    )


@router.post("/session", response_model=Branch3Response)
def session(request: SessionRequest) -> Branch3Response:
    """Classify a whole session as benign or a session-level attack."""
    return run_branch3(request.queries)
