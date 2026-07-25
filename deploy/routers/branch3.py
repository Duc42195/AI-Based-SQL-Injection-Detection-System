"""Branch 3 — session-level sequence model. STUB until the model is trained.

Owner: Toi. When the model lands, load it via the registry and fill
``session_label`` / ``is_attack`` — the response shape already matches the
contract the frontend is built against.
"""

from __future__ import annotations

from fastapi import APIRouter

from deploy.schemas import Branch3Response, SessionRequest

router = APIRouter(prefix="/branch3", tags=["branch3"])


def run_branch3(queries: list[str]) -> Branch3Response:
    """Return the Branch-3 session result (not_ready stub for now)."""
    return Branch3Response(
        status="not_ready",
        detail="Branch-3 session model not trained yet.",
    )


@router.post("/session", response_model=Branch3Response)
def session(request: SessionRequest) -> Branch3Response:
    """Classify a whole session as benign or a session-level attack (stub)."""
    return run_branch3(request.queries)
