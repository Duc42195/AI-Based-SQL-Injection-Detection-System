"""Tests for PSI drift detection."""

from __future__ import annotations

import numpy as np
import pytest

from src.monitoring.drift import (
    classify,
    detect_trigger,
    fit_reference_bins,
    iter_windows,
    psi,
    psi_categorical,
    psi_from_reference,
)


def _normal(n: int, loc: float = 0.0, scale: float = 1.0, seed: int = 0) -> list[float]:
    return np.random.default_rng(seed).normal(loc, scale, n).tolist()


# --------------------------------------------------------------------------- #
# Continuous PSI
# --------------------------------------------------------------------------- #
def test_identical_distribution_scores_near_zero() -> None:
    sample = _normal(5000)
    assert psi(sample, sample) == pytest.approx(0.0, abs=1e-9)


def test_same_distribution_different_draw_stays_stable() -> None:
    value = psi(_normal(5000, seed=1), _normal(5000, seed=2))
    assert value < 0.1, f"independent draws of one distribution should be stable, got {value}"


def test_shifted_distribution_registers_significant_drift() -> None:
    value = psi(_normal(5000, loc=0.0, seed=1), _normal(5000, loc=3.0, seed=2))
    assert value > 0.2, f"a 3-sigma shift should be significant, got {value}"


def test_psi_grows_monotonically_with_the_shift() -> None:
    reference = _normal(5000, seed=1)
    values = [
        psi(reference, _normal(5000, loc=shift, seed=2)) for shift in (0.0, 0.5, 1.0, 2.0)
    ]
    assert values == sorted(values), f"PSI should increase with the shift, got {values}"


def test_reference_bins_are_reused_across_windows() -> None:
    """Scoring via fitted bins must equal the one-shot helper."""
    reference = _normal(4000, seed=1)
    current = _normal(1000, loc=1.0, seed=2)
    bins = fit_reference_bins(reference, feature="x", n_bins=10)
    assert psi_from_reference(current, bins) == pytest.approx(
        psi(reference, current), rel=1e-9
    )


def test_empty_bin_is_floored_not_dropped() -> None:
    """A current window missing a whole region must not silently score 0."""
    reference = list(np.linspace(0, 10, 1000))
    current = list(np.linspace(0, 1, 1000))  # collapsed into the lowest region
    assert psi(reference, current) > 0.2


def test_extreme_unseen_values_fall_into_the_end_bins() -> None:
    """Open outer edges: out-of-range values must be counted, not discarded."""
    bins = fit_reference_bins(list(np.linspace(0, 1, 1000)), n_bins=10)
    # Every observation is far outside the reference range.
    assert psi_from_reference([99.0] * 500, bins) > 0.2


def test_constant_feature_does_not_blow_up() -> None:
    bins = fit_reference_bins([5.0] * 100, n_bins=10)
    assert psi_from_reference([5.0] * 50, bins) == pytest.approx(0.0, abs=1e-6)


def test_empty_window_is_reported_as_no_information() -> None:
    bins = fit_reference_bins(_normal(1000), n_bins=10)
    assert np.isfinite(psi_from_reference([], bins))


def test_fitting_on_an_empty_sample_is_an_error() -> None:
    with pytest.raises(ValueError):
        fit_reference_bins([])


# --------------------------------------------------------------------------- #
# Categorical PSI
# --------------------------------------------------------------------------- #
def test_categorical_identical_is_zero() -> None:
    shares = {"normal": 0.9, "union_based": 0.1}
    assert psi_categorical(shares, shares) == pytest.approx(0.0, abs=1e-9)


def test_categorical_new_class_registers_drift() -> None:
    before = {"normal": 0.95, "union_based": 0.05}
    after = {"normal": 0.80, "union_based": 0.05, "stacked": 0.15}
    assert psi_categorical(before, after) > 0.2


def test_categorical_accepts_raw_label_sequences() -> None:
    before = ["normal"] * 90 + ["union_based"] * 10
    after = ["normal"] * 50 + ["union_based"] * 50
    assert psi_categorical(before, after) > 0.2


# --------------------------------------------------------------------------- #
# Bands and trigger
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value,expected", [(0.05, "stable"), (0.15, "moderate"), (0.35, "significant")]
)
def test_classify_bands(value: float, expected: str) -> None:
    assert classify(value) == expected


def _window(index: int, **psi_values: float) -> dict:
    return {"index": index, "psi": psi_values}


def test_trigger_requires_consecutive_breaches() -> None:
    windows = [
        _window(0, **{"global": 0.05}),
        _window(1, **{"global": 0.30}),  # single spike -> not enough
        _window(2, **{"global": 0.05}),
    ]
    assert detect_trigger(windows, sustained=2, signals=["global"]).fired is False


def test_trigger_fires_on_a_sustained_breach() -> None:
    windows = [
        _window(0, **{"global": 0.05}),
        _window(1, **{"global": 0.30}),
        _window(2, **{"global": 0.31}),
    ]
    trigger = detect_trigger(windows, sustained=2, signals=["global"])
    assert trigger.fired is True
    assert trigger.window_index == 2
    assert trigger.signal == "global"


def test_trigger_reports_the_earliest_firing_signal() -> None:
    """Subpopulation drift often precedes global drift; report the first one."""
    windows = [
        _window(0, **{"global": 0.01, "attack_subpop": 0.30}),
        _window(1, **{"global": 0.01, "attack_subpop": 0.31}),
        _window(2, **{"global": 0.30, "attack_subpop": 0.32}),
        _window(3, **{"global": 0.31, "attack_subpop": 0.33}),
    ]
    trigger = detect_trigger(
        windows, sustained=2, signals=["global", "attack_subpop"]
    )
    assert trigger.fired is True
    assert trigger.signal == "attack_subpop"
    assert trigger.window_index == 1


def test_quiet_series_never_fires() -> None:
    windows = [_window(i, **{"global": 0.02}) for i in range(20)]
    assert detect_trigger(windows).fired is False


# --------------------------------------------------------------------------- #
# Windowing
# --------------------------------------------------------------------------- #
def test_iter_windows_covers_every_row_once() -> None:
    windows = list(iter_windows(2500, 1000))
    assert [w[0] for w in windows] == [0, 1, 2]
    assert windows[-1] == (2, 2000, 2500)  # trailing partial window kept
    assert sum(stop - start for _, start, stop in windows) == 2500
