"""Data page — the review queue, backed by real storage.

Implements section 6 of ``report/plan/mlops_contract.md``. Items arrive carrying
the model's own prediction as ``ai_label``, so review is acceptance or
correction rather than annotation from scratch. Confirmed labels append to the
ledger that feeds the next data version.

Branch 1 is wired; Branches 2 and 3 report empty queues until their loops exist.
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
from src.decision.queue import (
    append_confirmed,
    confirmed_labels_path,
    open_queue,
    read_confirmed,
)
from src.preprocessing.multiclass_tagger import LABEL_NAMES
from src.utils import get_logger, load_config

logger = get_logger(__name__)

router = APIRouter(prefix="/data", tags=["data"])

_LABEL_IDS = {name: label for label, name in LABEL_NAMES.items()}

# Mock pools per task. Real impl reads from the continual-learning stores.
_UNANNOTATED: dict[str, list[dict]] = {
    "branch1": [
        {"id": "u_n1_001", "query": "1' OR 1=1-- -", "source": "overkill_queue"},
        {"id": "u_n1_002", "query": "'; WAITFOR DELAY '0:0:5'--", "source": "overkill_queue"},
        {"id": "u_n1_003", "query": "SELECT price FROM items WHERE id = 88", "source": "low_confidence"},
    ],
    "branch2": [
        {"id": "u_n2_001", "query": "GET /admin/../../etc/passwd", "source": "high_anomaly"},
        {"id": "u_n2_002", "query": "SELECT * FROM orders JOIN users USING(uid)", "source": "high_anomaly"},
    ],
    "branch3": [
        {"id": "u_n3_001", "query": "step1: id=1 AND 1=1 | step2: id=1 AND 1=2", "source": "session_replay"},
    ],
}

_ANNOTATED_COUNT: dict[str, int] = {"branch1": 12480, "branch2": 9130, "branch3": 640}


@router.get("/{task}/unannotated", response_model=UnannotatedResponse)
def unannotated(
    task: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> UnannotatedResponse:
    """List queries awaiting review, each with the model's proposed label."""
    validate_task(task)
    options = label_options(task)
    if task != "branch1":
        return UnannotatedResponse(task=task, count=0, items=[], label_options=options)

    cfg = load_config()
    queue = open_queue(cfg)
    pending = queue.list(status="pending", limit=limit, offset=offset)
    return UnannotatedResponse(
        task=task,
        count=queue.counts().get("pending", 0),
        items=[
            UnannotatedItem(
                id=item.id,
                query=item.query_raw,
                source=item.source,
                ai_label=item.ai_label,
                ai_confidence=item.ai_confidence,
                anomaly_score=item.anomaly_score,
            )
            for item in pending
        ],
        label_options=options,
        acceptance_rate=queue.acceptance_rate(),
    )


@router.get("/{task}/annotated", response_model=AnnotatedResponse)
def annotated(
    task: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> AnnotatedResponse:
    """List confirmed labels from the ledger that feeds the next data version."""
    validate_task(task)
    if task != "branch1":
        return AnnotatedResponse(task=task, count=0, items=[])

    cfg = load_config()
    records = read_confirmed(confirmed_labels_path(cfg))
    page = records[offset : offset + limit]
    return AnnotatedResponse(
        task=task,
        count=len(records),
        items=[
            AnnotatedItem(
                id=str(record.get("id", "")),
                query=str(record.get("query_canonical", "")),
                label=str(record.get("label", "")),
                annotated_at=str(record.get("confirmed_at", "")),
                ai_label=record.get("ai_label"),
                was_corrected=bool(record.get("was_corrected", False)),
            )
            for record in page
        ],
        corrected=sum(1 for r in records if r.get("was_corrected")),
    )


@router.post("/{task}/annotate", response_model=AnnotateResponse)
def annotate(task: str, request: AnnotateRequest) -> AnnotateResponse:
    """Approve, correct or reject one queued item.

    ``action="approve"`` accepts the model's proposed label; ``"correct"``
    requires a label; ``"reject"`` drops the sample so it never trains anything.
    """
    validate_task(task)
    if task != "branch1":
        raise HTTPException(status_code=409, detail=f"No review queue for {task} yet.")

    options = label_options(task)
    if request.action == "correct" and request.label not in options:
        raise HTTPException(
            status_code=422,
            detail=f"Label '{request.label}' not in {options} for task '{task}'.",
        )

    cfg = load_config()
    queue = open_queue(cfg)
    try:
        item = queue.decide(
            request.id, request.action, label=request.label, decided_by="admin"
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No review item {request.id!r}.")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    written = append_confirmed([item], confirmed_labels_path(cfg), label_ids=_LABEL_IDS)
    return AnnotateResponse(
        ok=True,
        id=item.id,
        label=item.final_label or "",
        status=item.status,
        was_corrected=item.was_corrected,
        persisted=written > 0,
        acceptance_rate=queue.acceptance_rate(),
    )
