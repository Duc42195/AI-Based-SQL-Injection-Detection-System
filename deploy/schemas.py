"""Pydantic request/response models — the stable contract for the Streamlit client.

Keep these shapes stable: the frontend (Minh) builds against them before the
Branch-2/3 models exist. Branches that aren't trained yet return the same object
shape with ``status="not_ready"`` so the UI can render a placeholder instead of
handling an HTTP error.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

BranchStatus = Literal["ready", "not_ready"]
DecisionAction = Literal["BLOCK", "OVERKILL", "ALLOW", "UNKNOWN"]


# --------------------------------------------------------------------------- #
# Requests
# --------------------------------------------------------------------------- #
class QueryRequest(BaseModel):
    """A single query/parameter string to analyse."""

    query: str = Field(..., min_length=1, description="Raw query/parameter string.")


class SessionRequest(BaseModel):
    """An ordered list of queries forming one session (Branch 3)."""

    queries: list[str] = Field(
        ..., min_length=1, description="Ordered queries in the session."
    )


# --------------------------------------------------------------------------- #
# Per-branch responses
# --------------------------------------------------------------------------- #
class Nhanh1Response(BaseModel):
    """Branch-1 supervised multiclass result."""

    status: BranchStatus = "ready"
    query_canonical: str | None = None
    label: int | None = None
    label_name: str | None = None
    is_sqli: bool | None = None
    # Top predicted class probability (how sure of the specific class).
    confidence: float | None = None
    # Combined probability of any attack class (1 - P(normal)); this is what
    # `is_sqli` is thresholded on, so display it alongside `threshold`.
    attack_probability: float | None = None
    probabilities: dict[str, float] | None = None
    threshold: float | None = None
    detail: str | None = None


class Nhanh2Response(BaseModel):
    """Branch-2 anomaly result (stub until the model is trained)."""

    status: BranchStatus = "not_ready"
    anomaly_score: float | None = None
    is_anomaly: bool | None = None
    detail: str | None = None


class Nhanh3Response(BaseModel):
    """Branch-3 session-level result (stub until the model is trained)."""

    status: BranchStatus = "not_ready"
    session_label: str | None = None
    is_attack: bool | None = None
    detail: str | None = None


# --------------------------------------------------------------------------- #
# Fusion / decision
# --------------------------------------------------------------------------- #
class Decision(BaseModel):
    """Final action from the decision matrix over the available branches."""

    action: DecisionAction
    reason: str


class DetectResponse(BaseModel):
    """Unified response: all branches + fused decision (the system flow)."""

    query_canonical: str | None = None
    nhanh1: Nhanh1Response
    nhanh2: Nhanh2Response
    nhanh3: Nhanh3Response
    decision: Decision


# --------------------------------------------------------------------------- #
# Ops
# --------------------------------------------------------------------------- #
class HealthResponse(BaseModel):
    """Liveness + per-branch readiness."""

    status: Literal["ok"] = "ok"
    api_version: str
    branches: dict[str, str]


class MetricsResponse(BaseModel):
    """Evaluation metrics for a branch (served from a report/metadata JSON)."""

    status: Literal["ready", "not_ready"] = "ready"
    source: str | None = None
    metrics: dict | None = None
    detail: str | None = None


class OverkillItem(BaseModel):
    """One entry in the Admin overkill review queue."""

    id: str
    query: str
    reason: str
    created_at: str


class OverkillQueueResponse(BaseModel):
    """Pending items awaiting Admin confirmation (stub storage for now)."""

    items: list[OverkillItem] = Field(default_factory=list)
    count: int = 0


class OverkillActionResponse(BaseModel):
    """Result of confirming/rejecting an overkill item."""

    ok: bool
    id: str
    action: Literal["confirm", "reject"]
    # False until real SQLite persistence (src/decision/) lands.
    persisted: bool = False


# --------------------------------------------------------------------------- #
# Test page — demo (intentionally-vulnerable) database
# --------------------------------------------------------------------------- #
class DemoDatabaseResponse(BaseModel):
    """The seeded demo table shown on the Test page."""

    table: str
    columns: list[str]
    rows: list[dict]
    row_count: int
    query_template: str


class DemoExecuteRequest(BaseModel):
    """One or two user inputs (2 = a session for Branch 3), and the mode."""

    inputs: list[str] = Field(..., min_length=1, max_length=2)
    # False = run raw against the DB (no protection); True = run detection first.
    protected: bool = False


class DemoStepResult(BaseModel):
    """Outcome for a single input in a demo execution."""

    input: str
    constructed_sql: str
    executed: bool
    row_count: int
    leaked: bool
    rows: list[dict] = Field(default_factory=list)
    error: str | None = None
    nhanh1: Nhanh1Response | None = None
    nhanh2: Nhanh2Response | None = None


class DemoExecuteResponse(BaseModel):
    """Result of the 'no model' / 'with model' demo buttons."""

    protected: bool
    results: list[DemoStepResult]
    nhanh3: Nhanh3Response | None = None
    decision: Decision | None = None


# --------------------------------------------------------------------------- #
# Monitor page
# --------------------------------------------------------------------------- #
class DriftPoint(BaseModel):
    """One drift measurement in time."""

    date: str
    value: float


class DriftResponse(BaseModel):
    """Drift time-series for one task + alert state."""

    task: str
    metric: str
    threshold: float
    alert: bool
    points: list[DriftPoint]


class RetrainResponse(BaseModel):
    """Result of triggering a retrain for a task."""

    ok: bool
    task: str
    job_id: str
    status: Literal["queued"] = "queued"


class LogsResponse(BaseModel):
    """Recent log lines for a task."""

    task: str
    lines: list[str]


# --------------------------------------------------------------------------- #
# Data page — annotation
# --------------------------------------------------------------------------- #
class UnannotatedItem(BaseModel):
    """A sample awaiting a label."""

    id: str
    query: str
    source: str


class UnannotatedResponse(BaseModel):
    """A page of unannotated samples + the label choices for this task."""

    task: str
    count: int
    items: list[UnannotatedItem]
    label_options: list[str]


class AnnotatedItem(BaseModel):
    """A sample that already has a label."""

    id: str
    query: str
    label: str
    annotated_at: str


class AnnotatedResponse(BaseModel):
    """A page of annotated samples."""

    task: str
    count: int
    items: list[AnnotatedItem]


class AnnotateRequest(BaseModel):
    """Assign a label to one unannotated sample."""

    id: str
    label: str


class AnnotateResponse(BaseModel):
    """Result of an annotation (not persisted until continual-learning lands)."""

    ok: bool
    id: str
    label: str
    persisted: bool = False


# --------------------------------------------------------------------------- #
# Train page
# --------------------------------------------------------------------------- #
class TrainStartRequest(BaseModel):
    """Train/valid/test split percentages (should sum to 100)."""

    train: int = Field(70, ge=1, le=98)
    valid: int = Field(15, ge=1, le=98)
    test: int = Field(15, ge=1, le=98)


class TrainStartResponse(BaseModel):
    """Handle for a started (simulated) training job."""

    job_id: str
    task: str
    status: Literal["running"] = "running"
    total_epochs: int


class LossPoint(BaseModel):
    """Train/valid loss at one epoch."""

    epoch: int
    train_loss: float
    valid_loss: float


class TrainStatusResponse(BaseModel):
    """Live status of a training job (poll while status == 'running')."""

    job_id: str
    task: str
    status: Literal["running", "done", "failed"]
    epoch: int
    total_epochs: int
    loss_curve: list[LossPoint]
    logs: list[str]


class TrainResultResponse(BaseModel):
    """Final metrics + confusion matrix once training is done."""

    job_id: str
    task: str
    status: Literal["done", "running", "failed"]
    labels: list[str] | None = None
    confusion_matrix: list[list[int]] | None = None
    metrics: dict | None = None
    saved_version: str | None = None
    detail: str | None = None
