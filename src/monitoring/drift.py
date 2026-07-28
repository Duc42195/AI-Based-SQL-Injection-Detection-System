"""Population Stability Index (PSI) for concept-drift monitoring.

Implements section 5 of ``report/plan/mlops_contract.md``.

PSI compares a *current* distribution against a *reference* one:

    PSI = Σ (cur_frac - ref_frac) · ln(cur_frac / ref_frac)

Conventional bands: < 0.1 stable · 0.1–0.2 moderate · > 0.2 significant
(``monitoring.psi_alert_threshold``).

Two design points matter more than the formula:

1. **Bin edges are fitted once on the reference and then reused.** Re-deriving
   them per window would rescale the axis every time and make windows
   incomparable — the series would measure the binning, not the drift.
2. **Empty bins are floored, not dropped.** ``ln(0)`` is undefined and simply
   skipping a bin silently understates drift, which is the opposite of what a
   monitor is for. A bin that was populated in the reference and is empty now is
   exactly the signal worth catching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

import numpy as np

from src.utils import get_logger

logger = get_logger(__name__)

# Floor applied to empty bins so the log stays finite. Small enough not to mask
# real movement, large enough to keep a single empty bin from dominating.
EPSILON = 1e-6


@dataclass
class ReferenceBins:
    """Bin edges fitted on a reference sample, plus its reference fractions.

    Persisted alongside a data version so later windows are scored on exactly
    the axis the reference defined.
    """

    feature: str
    edges: list[float]
    reference_fractions: list[float]

    def to_dict(self) -> dict:
        """Serialise for the drift record."""
        return {
            "feature": self.feature,
            "edges": list(self.edges),
            "reference_fractions": list(self.reference_fractions),
        }

    @classmethod
    def from_dict(cls, raw: Mapping) -> ReferenceBins:
        """Rebuild from a persisted drift record."""
        return cls(
            feature=raw["feature"],
            edges=list(raw["edges"]),
            reference_fractions=list(raw["reference_fractions"]),
        )


def _fractions(values: Sequence[float], edges: Sequence[float]) -> np.ndarray:
    """Bucket values into ``edges`` and return the fraction per bin."""
    counts, _ = np.histogram(np.asarray(values, dtype=float), bins=edges)
    total = counts.sum()
    if total == 0:
        # No observations: report a uniform distribution rather than NaNs, so a
        # caller charting an empty window sees "no information", not a spike.
        return np.full(len(counts), 1.0 / len(counts))
    return counts / total


def fit_reference_bins(
    values: Sequence[float], feature: str = "value", n_bins: int = 10
) -> ReferenceBins:
    """Fit quantile bin edges on a reference sample.

    Quantiles (rather than equal-width bins) keep every bin populated for
    skewed features such as query length, where equal-width binning would put
    almost everything in one bucket.

    Args:
        values: Reference observations.
        feature: Name recorded on the result.
        n_bins: Target number of bins.

    Returns:
        Fitted :class:`ReferenceBins`.

    Raises:
        ValueError: If ``values`` is empty.
    """
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        raise ValueError("Cannot fit reference bins on an empty sample")

    quantiles = np.linspace(0, 1, n_bins + 1)
    edges = np.unique(np.quantile(array, quantiles))
    if edges.size < 2:
        # A constant feature: one bin spanning the value, so PSI stays defined.
        edges = np.array([array[0] - 0.5, array[0] + 0.5])
    # Open the outer edges so unseen extremes fall in the end bins instead of
    # being dropped by np.histogram.
    edges = edges.astype(float)
    edges[0], edges[-1] = -np.inf, np.inf

    return ReferenceBins(
        feature=feature,
        edges=edges.tolist(),
        reference_fractions=_fractions(array, edges).tolist(),
    )


def psi_from_reference(values: Sequence[float], reference: ReferenceBins) -> float:
    """Score a sample against fitted reference bins.

    Args:
        values: Current-window observations.
        reference: Bins fitted by :func:`fit_reference_bins`.

    Returns:
        The PSI value (0.0 for an identical distribution).
    """
    current = _fractions(values, reference.edges)
    ref = np.asarray(reference.reference_fractions, dtype=float)
    cur = np.maximum(current, EPSILON)
    ref = np.maximum(ref, EPSILON)
    return float(np.sum((cur - ref) * np.log(cur / ref)))


def psi(
    reference_values: Sequence[float], current_values: Sequence[float], n_bins: int = 10
) -> float:
    """Convenience one-shot PSI between two samples.

    Prefer :func:`fit_reference_bins` + :func:`psi_from_reference` when scoring
    many windows against one reference, so the bins are fitted only once.
    """
    return psi_from_reference(
        current_values, fit_reference_bins(reference_values, n_bins=n_bins)
    )


def psi_categorical(
    reference: Mapping[str, float] | Sequence[str],
    current: Mapping[str, float] | Sequence[str],
) -> float:
    """PSI over a categorical distribution (e.g. predicted-class shares).

    Accepts either raw label sequences or pre-computed share mappings. Labels
    present in only one of the two are included, which is the point: a class
    that appears for the first time should register as drift.
    """
    ref_shares = _as_shares(reference)
    cur_shares = _as_shares(current)
    keys = set(ref_shares) | set(cur_shares)
    total = 0.0
    for key in keys:
        ref = max(ref_shares.get(key, 0.0), EPSILON)
        cur = max(cur_shares.get(key, 0.0), EPSILON)
        total += (cur - ref) * np.log(cur / ref)
    return float(total)


def _as_shares(data: Mapping[str, float] | Sequence[str]) -> dict[str, float]:
    """Normalise either a label sequence or a share mapping into shares."""
    if isinstance(data, Mapping):
        total = sum(data.values())
        if total <= 0:
            return {k: 0.0 for k in data}
        return {k: v / total for k, v in data.items()}
    labels = list(data)
    if not labels:
        return {}
    counts: dict[str, float] = {}
    for label in labels:
        counts[str(label)] = counts.get(str(label), 0.0) + 1.0
    return {k: v / len(labels) for k, v in counts.items()}


def classify(value: float, threshold: float = 0.2) -> str:
    """Return the conventional band for a PSI value."""
    if value < 0.1:
        return "stable"
    if value < threshold:
        return "moderate"
    return "significant"


@dataclass
class DriftTrigger:
    """Outcome of scanning a window series for a sustained breach."""

    fired: bool = False
    window_index: int | None = None
    signal: str | None = None
    sustained_windows: int = 0

    def to_dict(self) -> dict:
        """Serialise for the drift record."""
        return {
            "fired": self.fired,
            "window_index": self.window_index,
            "signal": self.signal,
            "sustained_windows": self.sustained_windows,
        }


def detect_trigger(
    windows: Sequence[Mapping],
    *,
    threshold: float = 0.2,
    sustained: int = 2,
    signals: Iterable[str] = ("global", "attack_subpop", "prediction"),
) -> DriftTrigger:
    """Find the first signal that breaches the threshold for N consecutive windows.

    A single-window spike is noise; requiring consecutive breaches is what makes
    the trigger actionable.

    Args:
        windows: Window records, each with a ``psi`` mapping of signal -> value.
        threshold: Alert threshold.
        sustained: Consecutive breaching windows required.
        signals: Signal names to scan, in priority order.

    Returns:
        A :class:`DriftTrigger`; ``fired`` is False if nothing sustained a breach.
    """
    best = DriftTrigger()
    for signal in signals:
        run = 0
        for window in windows:
            value = float(window.get("psi", {}).get(signal, 0.0))
            run = run + 1 if value >= threshold else 0
            if run >= sustained:
                index = int(window.get("index", 0))
                # Keep the earliest firing across signals so the reported
                # trigger is the first moment the system could have reacted.
                if best.window_index is None or index < best.window_index:
                    best = DriftTrigger(
                        fired=True,
                        window_index=index,
                        signal=signal,
                        sustained_windows=sustained,
                    )
                break
    return best


def iter_windows(n_rows: int, window_size: int) -> Iterable[tuple[int, int, int]]:
    """Yield ``(index, start, stop)`` for each full-or-partial window."""
    index = 0
    for start in range(0, n_rows, window_size):
        yield index, start, min(start + window_size, n_rows)
        index += 1
