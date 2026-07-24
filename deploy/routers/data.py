"""Data page — annotation queues, one tab per task.

MOCK DATA: unannotated/annotated pools are synthesised in-memory. The real
"unannotated" source is the Overkill queue + confirmed labels store
(src/continual_learning); swap ``_UNANNOTATED`` / ``_annotate`` for those when
they land. Shapes are the stable contract.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from deploy.schemas import (
    AnnotatedItem,
    AnnotatedResponse,
    AnnotateRequest,
    AnnotateResponse,
    UnannotatedItem,
    UnannotatedResponse,
)
from deploy.tasks import label_options, validate_task

router = APIRouter(prefix="/data", tags=["data"])

# Mock pools per task. Real impl reads from the continual-learning stores.
_UNANNOTATED: dict[str, list[dict]] = {
    "nhanh1": [
        {"id": "u_n1_001", "query": "1' OR 1=1-- -", "source": "overkill_queue"},
        {"id": "u_n1_002", "query": "'; WAITFOR DELAY '0:0:5'--", "source": "overkill_queue"},
        {"id": "u_n1_003", "query": "SELECT price FROM items WHERE id = 88", "source": "low_confidence"},
    ],
    "nhanh2": [
        {"id": "u_n2_001", "query": "GET /admin/../../etc/passwd", "source": "high_anomaly"},
        {"id": "u_n2_002", "query": "SELECT * FROM orders JOIN users USING(uid)", "source": "high_anomaly"},
    ],
    "nhanh3": [
        {"id": "u_n3_001", "query": "step1: id=1 AND 1=1 | step2: id=1 AND 1=2", "source": "session_replay"},
    ],
}

_ANNOTATED_COUNT: dict[str, int] = {"nhanh1": 12480, "nhanh2": 9130, "nhanh3": 640}


@router.get("/{task}/unannotated", response_model=UnannotatedResponse)
def unannotated(
    task: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> UnannotatedResponse:
    """List samples awaiting a label, plus the label choices for this task."""
    validate_task(task)
    pool = _UNANNOTATED.get(task, [])
    page = pool[offset : offset + limit]
    return UnannotatedResponse(
        task=task,
        count=len(pool),
        items=[UnannotatedItem(**item) for item in page],
        label_options=label_options(task),
    )


@router.get("/{task}/annotated", response_model=AnnotatedResponse)
def annotated(
    task: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> AnnotatedResponse:
    """List already-labelled samples (mock sample rows)."""
    validate_task(task)
    total = _ANNOTATED_COUNT.get(task, 0)
    opts = label_options(task)
    items = [
        AnnotatedItem(
            id=f"a_{task}_{offset + i:04d}",
            query=f"-- sample #{offset + i} for {task} --",
            label=opts[(offset + i) % len(opts)],
            annotated_at="2026-07-15T10:00:00",
        )
        for i in range(min(limit, max(0, total - offset)))
    ]
    return AnnotatedResponse(task=task, count=total, items=items)


@router.post("/{task}/annotate", response_model=AnnotateResponse)
def annotate(task: str, request: AnnotateRequest) -> AnnotateResponse:
    """Assign a label to one sample (stub: validated but not persisted).

    Validates the label against the task's vocabulary so the UI catches bad
    input; real persistence lands with the continual-learning store.
    """
    validate_task(task)
    opts = label_options(task)
    if request.label not in opts:
        raise HTTPException(
            status_code=422,
            detail=f"Label '{request.label}' not in {opts} for task '{task}'.",
        )
    # Real impl: append {id, label, annotated_at} to the continual-learning store.
    return AnnotateResponse(ok=True, id=request.id, label=request.label)
