"""Test page — demo DB view + 'no model' vs 'with model' execution.

Shows the core value proposition: a payload dumps the users table when run
directly (no model), but the detector blocks it before execution (with model).
Reuses the branch runners and decision fusion so the 'with model' path is
identical to ``/detect``.
"""

from __future__ import annotations

from fastapi import APIRouter

from deploy import demo_db
from deploy.routers.detect import fuse_decision
from deploy.routers.nhanh1 import run_nhanh1
from deploy.routers.nhanh2 import run_nhanh2
from deploy.routers.nhanh3 import run_nhanh3
from deploy.schemas import (
    DemoDatabaseResponse,
    DemoExecuteRequest,
    DemoExecuteResponse,
    DemoStepResult,
)

router = APIRouter(prefix="/demo", tags=["demo"])


@router.get("/database", response_model=DemoDatabaseResponse)
def database() -> DemoDatabaseResponse:
    """Return the seeded (fake) demo table for display."""
    return DemoDatabaseResponse(**demo_db.get_table())


@router.post("/execute", response_model=DemoExecuteResponse)
def execute(request: DemoExecuteRequest) -> DemoExecuteResponse:
    """Run inputs against the demo DB, optionally behind the detector.

    - ``protected=False``: build the SQL and run it raw — the attack succeeds
      and leaked rows are returned (the 'no model' button).
    - ``protected=True``: run detection first; execute only steps the detector
      allows (the 'with model' button).
    """
    results: list[DemoStepResult] = []
    nhanh1_responses = []

    for user_input in request.inputs:
        sql = demo_db.build_sql(user_input)
        if not request.protected:
            outcome = demo_db.execute_raw(user_input)
            results.append(
                DemoStepResult(
                    input=user_input,
                    constructed_sql=outcome["constructed_sql"],
                    executed=True,
                    row_count=outcome["row_count"],
                    leaked=outcome["leaked"],
                    rows=outcome["rows"],
                    error=outcome["error"],
                )
            )
            continue

        # Protected: classify the constructed SQL exactly as /detect does.
        n1 = run_nhanh1(sql)
        n2 = run_nhanh2(sql)
        nhanh1_responses.append(n1)
        blocked = n1.status == "ready" and bool(n1.is_sqli)
        outcome = None if blocked else demo_db.execute_raw(user_input)
        results.append(
            DemoStepResult(
                input=user_input,
                constructed_sql=sql,
                executed=outcome is not None,
                row_count=outcome["row_count"] if outcome else 0,
                leaked=outcome["leaked"] if outcome else False,
                rows=outcome["rows"] if outcome else [],
                error=outcome["error"] if outcome else None,
                nhanh1=n1,
                nhanh2=n2,
            )
        )

    if not request.protected:
        return DemoExecuteResponse(protected=False, results=results)

    # Fuse one decision over the session (Branch 3 sees the whole input list).
    nhanh3 = run_nhanh3(request.inputs)
    # Escalate to the worst per-step Branch-1 verdict for the fused decision.
    worst_n1 = _worst_nhanh1(nhanh1_responses)
    decision = fuse_decision(worst_n1, run_nhanh2(request.inputs[-1]), nhanh3)
    return DemoExecuteResponse(
        protected=True, results=results, nhanh3=nhanh3, decision=decision
    )


def _worst_nhanh1(responses):
    """Pick the most-severe Branch-1 response (an attack outranks normal)."""
    for resp in responses:
        if resp.status == "ready" and resp.is_sqli:
            return resp
    return responses[0]
