"""Admin overkill-review queue.

STUB storage for now: returns an empty queue and accepts confirm/reject without
persisting. Real SQLite storage (configs: ``decision.queue_path``) lands with
the decision layer in ``src/decision/`` (owner: Bach). The response shapes here
are the stable contract the Admin page is built against.
"""

from __future__ import annotations

from fastapi import APIRouter

from deploy.schemas import OverkillActionResponse, OverkillQueueResponse

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overkill-queue", response_model=OverkillQueueResponse)
def overkill_queue() -> OverkillQueueResponse:
    """List queries held for Admin review (empty until the queue is wired up)."""
    return OverkillQueueResponse(items=[], count=0)


@router.post("/overkill/{item_id}/confirm", response_model=OverkillActionResponse)
def confirm(item_id: str) -> OverkillActionResponse:
    """Confirm an overkill item as a real attack (stub: not persisted)."""
    return OverkillActionResponse(ok=True, id=item_id, action="confirm")


@router.post("/overkill/{item_id}/reject", response_model=OverkillActionResponse)
def reject(item_id: str) -> OverkillActionResponse:
    """Reject an overkill item as a false positive (stub: not persisted)."""
    return OverkillActionResponse(ok=True, id=item_id, action="reject")
