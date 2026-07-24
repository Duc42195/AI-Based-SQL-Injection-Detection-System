"""Branch 3 — session-level sequence model. STUB until the model is trained.

Owner: Toi. When the model lands, load it via the registry and fill
``session_label`` / ``is_attack`` — the response shape already matches the
contract the frontend is built against.
"""

from __future__ import annotations

from fastapi import APIRouter

from deploy.schemas import Nhanh3Response, SessionRequest

router = APIRouter(prefix="/nhanh3", tags=["nhanh3"])


def run_nhanh3(queries: list[str]) -> Nhanh3Response:
    """Return the Branch-3 session result (not_ready stub for now)."""
    return Nhanh3Response(
        status="not_ready",
        detail="Branch-3 session model not trained yet.",
    )


@router.post("/session", response_model=Nhanh3Response)
def session(request: SessionRequest) -> Nhanh3Response:
    """Classify a whole session as benign or a session-level attack (stub)."""
    return run_nhanh3(request.queries)
