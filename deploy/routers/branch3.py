"""Branch 3 / Session Correlator — session-level detection.

Not a trained model: re-uses Branch 1's classifier (content check on
concatenated session text) and Branch 2's anomaly detector (behavior check,
aggregating its per-query scores), correlated via
``src.models.branch3_session.SessionCorrelator``. See that module's
docstring and ``report/plan/data_contract.md`` §4.2 for why this replaced
the earlier GRU sequence-model design. Kept under the `/branch3` prefix for
backward compatibility with the existing config/API contract.
"""

from __future__ import annotations

from fastapi import APIRouter

from deploy.registry import get_registry
from deploy.schemas import Branch3Response, SessionRequest

router = APIRouter(prefix="/branch3", tags=["branch3"])


def run_branch3(queries: list[str]) -> Branch3Response:
    """Return the Session Correlator's result for one session's queries."""
    correlator = get_registry().branch3()
    if correlator is None:
        return Branch3Response(
            status="not_ready",
            detail="Session Correlator not calibrated yet (run train/calibrate_branch3.py).",
        )
    result = correlator.score(queries)
    return Branch3Response(
        status="ready",
        session_label=result["predicted_label"],
        is_attack=result["is_attack"],
        detail=(
            f"content_check={result['fires_content']} (attack_prob={result['attack_prob']:.3f}), "
            f"behavior_check={result['fires_behavior']} (mean_score={result['mean_score']:.3f}, "
            f"fraction_above={result['fraction_above']:.3f})"
        ),
    )


@router.post("/session", response_model=Branch3Response)
def session(request: SessionRequest) -> Branch3Response:
    """Classify a whole session as benign or a session-level attack."""
    return run_branch3(request.queries)
