"""Unified detection endpoint — runs all branches and fuses one verdict.

This is the end-to-end system flow: canonicalize -> Branch 1/2/3 -> apply the
decision matrix from the README (Vị trí B proxy policy). Branches not yet
trained contribute ``not_ready``; the decision degrades gracefully to whatever
signal is available, so the frontend gets a real verdict today and a richer one
as Branch 2/3 come online — with no client change.
"""

from __future__ import annotations

from fastapi import APIRouter

from deploy.routers.nhanh1 import run_nhanh1
from deploy.routers.nhanh2 import run_nhanh2
from deploy.routers.nhanh3 import run_nhanh3
from deploy.schemas import (
    Decision,
    DetectResponse,
    Nhanh1Response,
    Nhanh2Response,
    Nhanh3Response,
    QueryRequest,
)

router = APIRouter(tags=["detect"])


def fuse_decision(
    nhanh1: Nhanh1Response, nhanh2: Nhanh2Response, nhanh3: Nhanh3Response
) -> Decision:
    """Apply the per-query decision matrix over the available branches.

    Matrix (README): attack class -> BLOCK; Normal + anomaly=1 -> OVERKILL;
    Normal + anomaly=0 -> ALLOW. Branch 3 can escalate a benign query to
    BLOCK if the session is an attack. Missing branches degrade the verdict
    rather than block it.
    """
    # Branch 3 escalation (session-level) takes precedence when available.
    if nhanh3.status == "ready" and nhanh3.is_attack:
        return Decision(
            action="BLOCK",
            reason=f"Branch-3 flagged session as attack ({nhanh3.session_label}).",
        )

    if nhanh1.status != "ready":
        return Decision(
            action="UNKNOWN",
            reason="Branch-1 model not available; cannot decide.",
        )

    if nhanh1.is_sqli:
        return Decision(
            action="BLOCK",
            reason=f"Branch-1 detected attack class '{nhanh1.label_name}' "
            f"(confidence={nhanh1.confidence:.2f}).",
        )

    # Branch-1 says Normal — the anomaly branch decides ALLOW vs OVERKILL.
    if nhanh2.status == "ready" and nhanh2.is_anomaly:
        return Decision(
            action="OVERKILL",
            reason="Branch-1 Normal but Branch-2 flagged anomaly — hold for Admin.",
        )
    if nhanh2.status == "ready":
        return Decision(action="ALLOW", reason="Branch-1 Normal and no anomaly.")

    return Decision(
        action="ALLOW",
        reason="Branch-1 Normal; Branch-2 not available (OVERKILL undecidable).",
    )


@router.post("/detect", response_model=DetectResponse)
def detect(request: QueryRequest) -> DetectResponse:
    """Run the full pipeline on one query and return branches + fused decision."""
    nhanh1 = run_nhanh1(request.query)
    nhanh2 = run_nhanh2(request.query)
    nhanh3 = run_nhanh3([request.query])
    decision = fuse_decision(nhanh1, nhanh2, nhanh3)
    return DetectResponse(
        query_canonical=nhanh1.query_canonical,
        nhanh1=nhanh1,
        nhanh2=nhanh2,
        nhanh3=nhanh3,
        decision=decision,
    )
