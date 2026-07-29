"""Unified detection endpoint — runs all branches and fuses one verdict.

This is the end-to-end system flow: canonicalize -> Branch 1/2 -> apply the
decision matrix from the README (Position B proxy policy). Branches not yet
trained contribute ``not_ready``; the decision degrades gracefully to whatever
signal is available, so the frontend gets a real verdict today and a richer one
as Branch 2 comes online — with no client change.
"""

from __future__ import annotations

from fastapi import APIRouter

from deploy.routers.branch1 import run_branch1
from deploy.routers.branch2 import run_branch2
from deploy.schemas import (
    Decision,
    DetectResponse,
    Branch1Response,
    Branch2Response,
    QueryRequest,
)

router = APIRouter(tags=["detect"])


def fuse_decision(
    branch1: Branch1Response, branch2: Branch2Response
) -> Decision:
    """Apply the per-query decision matrix over the available branches.

    Matrix (README): attack class -> BLOCK; Normal + anomaly=1 -> OVERKILL;
    Normal + anomaly=0 -> ALLOW. Missing branches degrade the verdict rather
    than block it.
    """
    if branch1.status != "ready":
        return Decision(
            action="UNKNOWN",
            reason="Branch-1 model not available; cannot decide.",
        )

    if branch1.is_sqli:
        return Decision(
            action="BLOCK",
            reason=f"Branch-1 detected attack class '{branch1.label_name}' "
            f"(confidence={branch1.confidence:.2f}).",
        )

    # Branch-1 says Normal — the anomaly branch decides ALLOW vs OVERKILL.
    if branch2.status == "ready" and branch2.is_anomaly:
        return Decision(
            action="OVERKILL",
            reason="Branch-1 Normal but Branch-2 flagged anomaly — hold for Admin.",
        )
    if branch2.status == "ready":
        return Decision(action="ALLOW", reason="Branch-1 Normal and no anomaly.")

    return Decision(
        action="ALLOW",
        reason="Branch-1 Normal; Branch-2 not available (OVERKILL undecidable).",
    )


@router.post("/detect", response_model=DetectResponse)
def detect(request: QueryRequest) -> DetectResponse:
    """Run the full pipeline on one query and return branches + fused decision."""
    branch1 = run_branch1(request.query)
    branch2 = run_branch2(request.query)
    decision = fuse_decision(branch1, branch2)
    return DetectResponse(
        query_canonical=branch1.query_canonical,
        branch1=branch1,
        branch2=branch2,
        decision=decision,
    )
