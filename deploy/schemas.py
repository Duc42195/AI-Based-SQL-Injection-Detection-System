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
class Branch1Response(BaseModel):
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


class Branch2Response(BaseModel):
    """Branch-2 anomaly result."""

    status: BranchStatus = "not_ready"
    query_canonical: str | None = None
    anomaly_score: float | None = None
    is_anomaly: bool | None = None
    detail: str | None = None


class Branch3Response(BaseModel):
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
    branch1: Branch1Response
    branch2: Branch2Response
    branch3: Branch3Response
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
    branch1: Branch1Response | None = None
    branch2: Branch2Response | None = None


class DemoExecuteResponse(BaseModel):
    """Result of the 'no model' / 'with model' demo buttons."""

    protected: bool
    results: list[DemoStepResult]
    branch3: Branch3Response | None = None
    decision: Decision | None = None


# --------------------------------------------------------------------------- #
# Monitor page
# --------------------------------------------------------------------------- #
class DriftPoint(BaseModel):
    """One drift window: every monitored signal, plus operational rates."""

    date: str  # window label, e.g. "w12"
    value: float  # the strongest signal in this window, for a single-line chart
    index: int = 0
    phase: str = ""
    # Reference windows score ~0 against themselves; the UI shades them so they
    # are not mistaken for a quiet period that means something.
    is_reference: bool = False
    psi: dict[str, float] = Field(default_factory=dict)
    rates: dict[str, float] = Field(default_factory=dict)


class DriftResponse(BaseModel):
    """Drift series for one task, or a structured not_ready."""

    task: str
    metric: str
    threshold: float
    alert: bool
    status: BranchStatus = "ready"
    signals: list[str] = Field(default_factory=list)
    trigger: dict | None = None
    reference: str | None = None
    generated_at: str | None = None
    detail: str | None = None
    points: list[DriftPoint] = Field(default_factory=list)


class RetrainResponse(BaseModel):
    """Result of triggering a retrain for a task."""

    ok: bool
    task: str
    job_id: str
    # `job_id` is the run_id, so it can be looked up via /mlops/runs.
    status: str = "queued"
    detail: str | None = None


class LogsResponse(BaseModel):
    """Recent log lines for a task."""

    task: str
    lines: list[str]


# --------------------------------------------------------------------------- #
# Data page — annotation
# --------------------------------------------------------------------------- #
class UnannotatedItem(BaseModel):
    """A sample awaiting review, carrying the model's proposed label."""

    id: str
    query: str
    source: str
    # The AI pre-label: the reviewer accepts or corrects it rather than
    # labelling from scratch.
    ai_label: str | None = None
    ai_confidence: float | None = None
    anomaly_score: float | None = None


class UnannotatedResponse(BaseModel):
    """A page of items awaiting review + the label choices for this task."""

    task: str
    count: int
    items: list[UnannotatedItem]
    label_options: list[str]
    # Share of pre-labels accepted unchanged so far — a live measure of model
    # quality, not just bookkeeping.
    acceptance_rate: float | None = None


class AnnotatedItem(BaseModel):
    """A confirmed label."""

    id: str
    query: str
    label: str
    annotated_at: str
    ai_label: str | None = None
    was_corrected: bool = False


class AnnotatedResponse(BaseModel):
    """A page of confirmed labels."""

    task: str
    count: int
    items: list[AnnotatedItem]
    corrected: int = 0


class AnnotateRequest(BaseModel):
    """Review one queued item."""

    id: str
    action: Literal["approve", "correct", "reject"] = "approve"
    # Required only for "correct".
    label: str | None = None


class AnnotateResponse(BaseModel):
    """Result of a review decision."""

    ok: bool
    id: str
    label: str
    status: str = "approved"
    was_corrected: bool = False
    persisted: bool = False
    acceptance_rate: float | None = None


# --------------------------------------------------------------------------- #
# Train page
# --------------------------------------------------------------------------- #
class TrainStartRequest(BaseModel):
    """Train/valid/test split percentages (should sum to 100)."""

    train: int = Field(70, ge=1, le=98)
    valid: int = Field(15, ge=1, le=98)
    test: int = Field(15, ge=1, le=98)


class TrainStartResponse(BaseModel):
    """Handle for a started training job."""

    job_id: str
    task: str
    status: Literal["running"] = "running"
    total_epochs: int
    # False means the response is simulated and no model is written.
    real: bool = False


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
    real: bool = False


# --------------------------------------------------------------------------- #
# MLOps lifecycle
# --------------------------------------------------------------------------- #
class VersionsResponse(BaseModel):
    """The data-version registry with lineage."""

    dataset: str
    active_model: str
    versions: list[dict] = Field(default_factory=list)


class ReplayRequest(BaseModel):
    """Replay a slice of the held-out stream through the live model."""

    # Kept modest by default: a full 80k replay takes minutes and the demo only
    # needs enough windows to show a drift curve.
    limit: int | None = Field(20000, ge=100, le=200000)
    max_queue: int | None = Field(200, ge=1, le=5000)


class ReplayResponse(BaseModel):
    """Outcome of a replay: drift written, queue filled."""

    replayed: int
    windows: int
    queued: int
    alert: bool
    trigger: dict
    sources: list[str] = Field(default_factory=list)


class MlopsResetResponse(BaseModel):
    """What a demo reset restored and archived."""

    ok: bool
    baseline_model: str
    baseline_data_version: str
    archived_models: list[str] = Field(default_factory=list)
    purged_queue_rows: int = 0
    dropped_labels: int = 0
    removed_versions: list[str] = Field(default_factory=list)


class TrainResultResponse(BaseModel):
    """Final metrics, gate decision and promotion outcome."""

    job_id: str
    task: str
    status: Literal["done", "running", "failed"]
    labels: list[str] | None = None
    confusion_matrix: list[list[int]] | None = None
    metrics: dict | None = None
    saved_version: str | None = None
    detail: str | None = None
    real: bool = False
    # Real runs only: the sealed version, why it bumped, and the gate's verdict.
    data_version: str | None = None
    bump: str | None = None
    run_id: str | None = None
    run_status: str | None = None
    decision: dict | None = None
