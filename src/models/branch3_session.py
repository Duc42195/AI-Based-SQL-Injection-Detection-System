"""Branch 3 / Session Correlator — session-level detection.

**Current mechanism: `SessionCorrelator` (see below).** Not a trained model —
it re-uses Branch 1's classifier and Branch 2's anomaly detector exactly as
already trained, and correlates their signals across a session. No gradient
training, no weights of its own, only two calibrated scalar thresholds.

Two branches, run independently and OR'd together:
  - **Content check:** concatenate the session's raw query text (whole
    strings, not truncated) and re-score with Branch 1's existing classifier,
    against a `content_threshold` calibrated separately for this session-level
    check (see `calibrate()`'s docstring) — NOT Branch 1's single-query
    `decision_threshold` (0.5), which was only a placeholder before this
    calibration was added.
    Validated empirically (Experiment A2, this project's diagnostic session):
    a single `boolean_blind` bisection probe can sit just under Branch 1's
    0.5 single-query threshold (measured: 0.459 at step 1), but concatenating
    more of the session's real steps pushes the score up (0.593 at 10 steps,
    0.666 at 32) — because TF-IDF is a *relative*-frequency representation
    and bisection repeats near-identical SQL structure across steps, so
    concatenation reinforces the attack n-grams rather than diluting them
    with unrelated content. No retraining needed or attempted.
    **Precise mechanism (checked, not assumed):** concatenating only the WEAK
    steps together does NOT cross Branch 1's 0.5 single-query threshold on
    its own (a session's first 5 length-bisection steps, each 0.44-0.47
    alone, stay at 0.45-0.46 concatenated among themselves) — that threshold
    only gets crossed once growing `k` mixes in the STRONG
    character-extraction steps (each already 0.66-0.70 alone). However,
    benign TEST sessions' own concatenated content probability tops out at
    0.172 (Experiment D1) — a wide margin below the weak-attack
    concatenation's 0.45-0.46 — so a session-level `content_threshold`
    calibrated in that gap (comes out ~0.34-0.38 depending on the TRAIN
    split) lets the content check catch the weak-only case too, at no
    measured FPR cost. This threshold is *not* the same thing as retraining
    Branch 1 to recognize weak signal; it only changes what counts as
    "enough" attack probability for a whole session's concatenated text.
  - **Behavior check:** aggregate Branch 2's per-query anomaly scores across
    the session (mean, fraction above a benign-calibrated threshold).
    Branch 2 is called exactly as trained — per single query, in its
    original feature distribution — only the values are aggregated
    afterward, so there is no train/inference distribution mismatch here at
    all (unlike the content check, which does venture outside Branch 1's
    single-query training length but is empirically shown not to degrade).
    **Independently catches the same weak-step case as the (now-calibrated)
    content check above:** taking ONLY those same 5 weak-per-content-check
    steps and running the behavior check alone gives `mean_score = 2.171`
    against a calibrated `mean_threshold = -4.465` — fires clearly. Branch 2
    scores structural shape (length, special-char ratio, keyword count,
    entropy), not attack type, so a length-bisection query's nested
    `OR`/subquery syntax reads as anomalous regardless of Branch 1's
    confidence about the specific attack class. Both checks now cover this
    particular case on their own — intentional redundancy from OR'ing them,
    not a single point of failure. The one gap genuinely not covered: an
    attacker evading BOTH simultaneously (lexically benign-looking AND
    structurally benign-shaped) — a real, acknowledged limitation of reusing
    only Branch 1 + Branch 2's existing signals, not something fixable by
    reconfiguring this class.
    Validated empirically (Experiment B): benign vs. attack separates with
    AUC 0.998-1.0 using only these two aggregate statistics.

Why this replaced the original GRU sequence-model design: the GRU consumed
Branch 1's 5-class *probability* output per step, not its content embedding.
For a linear TF-IDF+LogReg Branch 1, those are NOT the same thing — the
probability vector is a lossy projection trained to separate attack *type*,
and empirically collapses the token-level differences between consecutive
bisection steps (two steps differing only in comparison bound had TF-IDF
cosine similarity 0.961 but near-identical post-classifier probabilities).
That information bottleneck, combined with the fact that Branch 1 already
blocks most real `boolean_blind`/`time_blind` sessions per-query in
production (so a session-level GRU rarely gets enough steps to matter) and
that no principled fixed `max_session_len` exists, is why the GRU design was
dropped entirely rather than kept as a fallback. Its code (`SessionSequenceDetector`,
`_GRUClassifier`) was removed once `SessionCorrelator` was validated and merged —
see git history (`git log -- src/models/branch3_session.py`) or
`report/plan/data_contract.md` §4.2 for the full write-up and original code.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from src.utils import get_logger

logger = get_logger(__name__)


class SessionCorrelator:
    """Correlates Branch 1 (content) and Branch 2 (behavior) signals over a session.

    Not trained by gradient descent — ``calibrate()`` only picks 3 scalar
    thresholds from a labeled train split. Re-uses the Branch 1
    vectorizer+classifier and the Branch 2 ``AnomalyDetector`` passed in at
    construction time (typically the already-trained ``branch1_v1``/
    ``branch2_v1`` artifacts loaded once by ``deploy/registry.py``) — it owns
    no model weights of its own.
    """

    def __init__(
        self,
        b1_vectorizer: Any,
        b1_clf: Any,
        b2_detector: Any,
        content_threshold: float = 0.5,
        per_query_threshold: float = 0.0,
        mean_threshold: float = 0.0,
        fraction_threshold: float = 0.0,
        max_decode_iterations: int = 3,
    ) -> None:
        """Initialise the correlator.

        Args:
            b1_vectorizer: Branch 1's fitted TF-IDF vectorizer.
            b1_clf: Branch 1's fitted classifier.
            b2_detector: A fitted ``src.models.branch2_anomaly.AnomalyDetector``.
            content_threshold: Attack-probability cutoff for the content
                check on concatenated session text. The constructor default
                is ``branch1_supervised.decision_threshold`` (reused as a
                placeholder pre-calibration); ``calibrate()`` overwrites it
                with a session-level value picked from TRAIN data, which
                empirically comes out lower than 0.5 (see ``calibrate()``'s
                docstring) — a session's concatenated text is held to a
                different, separately-justified cutoff than a single query.
            per_query_threshold: Branch-2 score above which one query counts
                toward ``fraction_above`` — calibrated from benign per-query
                scores in ``calibrate()``.
            mean_threshold: Behavior-check cutoff on the session's mean
                Branch-2 score — calibrated in ``calibrate()``.
            fraction_threshold: Behavior-check cutoff on the fraction of
                steps exceeding ``per_query_threshold`` — calibrated in
                ``calibrate()``.
            max_decode_iterations: Passed to ``canonicalize()`` on each raw
                query text before scoring (URL/hex/CHAR() decoding, keyword
                case-folding) — the same anti-evasion normalization
                ``Branch1Model``/``Branch2Model`` apply per query
                (``deploy/registry.py``), so a session isn't easier to evade
                than a single query would be.

        Note: the content check's predicted attack-type label always comes
        from Branch 1's OWN label schema (``src.preprocessing.multiclass_tagger.LABEL_NAMES``:
        0=normal,1=union_based,2=error_based,3=boolean_blind,4=time_blind) —
        there is deliberately no separate "session class names" parameter
        here. An earlier version of this class took one and indexed into it
        using a Branch-1 label id, which silently mislabeled every
        content-check hit (Branch-1 id 3 = boolean_blind, but session-schema
        id 3 = query_splitting — same integer, different meaning).
        """
        self.b1_vectorizer = b1_vectorizer
        self.b1_clf = b1_clf
        self.b2_detector = b2_detector
        self.content_threshold = content_threshold
        self.per_query_threshold = per_query_threshold
        self.mean_threshold = mean_threshold
        self.fraction_threshold = fraction_threshold
        self.max_decode_iterations = max_decode_iterations

    def calibrate(
        self,
        train_sessions: list[tuple[list[str], list[float], int]],
        percentile: float = 0.90,
    ) -> None:
        """Pick the content + 3 behavior thresholds from labeled TRAIN sessions only.

        Args:
            train_sessions: List of ``(query_texts, branch2_scores, label)``
                per session — ``label == 0`` marks benign. Must be the TRAIN
                split; evaluate on a disjoint TEST split to avoid leakage
                (see ``train/calibrate_branch3.py``).
            percentile: Percentile of benign per-query Branch-2 scores used
                as ``per_query_threshold`` (a query "counts as elevated" if
                its score exceeds this many benign queries' scores).

        Also calibrates ``self.content_threshold`` on the same TRAIN split,
        replacing the constructor's default (Branch 1's single-query
        ``decision_threshold``, reused as a placeholder). Found via
        diagnostic experiments after the initial merge: benign TEST
        sessions' concatenated content probability tops out at 0.172, while
        a `boolean_blind` session containing ONLY its weak length-bisection
        steps concatenates to 0.45-0.46 — comfortably below Branch 1's 0.5
        single-query threshold, so the content check missed exactly the
        sessions the behavior check was relied on to catch alone. A
        session-level threshold calibrated in this gap lets the content
        check independently catch that case too, at no measured FPR cost
        (see ``report/plan/data_contract.md`` §4.2).
        """
        from src.models.branch3_features import branch1_probabilities
        from src.preprocessing.canonicalize import canonicalize

        benign_scores = np.concatenate(
            [scores for _, scores, label in train_sessions if label == 0]
        )
        self.per_query_threshold = float(np.quantile(benign_scores, percentile))

        mean_vals, frac_vals, content_vals, labels = [], [], [], []
        for texts, scores, label in train_sessions:
            scores_arr = np.asarray(scores, dtype=np.float64)
            mean_vals.append(scores_arr.mean())
            frac_vals.append(float((scores_arr > self.per_query_threshold).mean()))

            canonical_texts = [canonicalize(t, self.max_decode_iterations).query_canonical for t in texts]
            concat_text = " ".join(canonical_texts)
            probs = branch1_probabilities([concat_text], self.b1_vectorizer, self.b1_clf)[0]
            content_vals.append(1.0 - probs[0])  # column 0 = "normal"

            labels.append(label)
        mean_vals = np.array(mean_vals)
        frac_vals = np.array(frac_vals)
        content_vals = np.array(content_vals)
        labels = np.array(labels)

        def _best_threshold(values: np.ndarray) -> float:
            """Max (TPR - FPR) over observed values — simple 1-D threshold search."""
            benign_vals, attack_vals = values[labels == 0], values[labels != 0]
            best_t, best_score = float(values.min()), -1.0
            for t in np.unique(values):
                score = (attack_vals >= t).mean() - (benign_vals >= t).mean()
                if score > best_score:
                    best_score, best_t = score, float(t)
            return best_t

        self.mean_threshold = _best_threshold(mean_vals)
        self.fraction_threshold = _best_threshold(frac_vals)
        self.content_threshold = _best_threshold(content_vals)
        logger.info(
            "Calibrated SessionCorrelator: content_threshold=%.4f per_query_threshold=%.4f "
            "mean_threshold=%.4f fraction_threshold=%.4f",
            self.content_threshold, self.per_query_threshold, self.mean_threshold, self.fraction_threshold,
        )

    def score(self, texts: list[str], branch2_scores: list[float] | None = None) -> dict:
        """Score one session: content check OR behavior check.

        Args:
            texts: Session's ``query_canonical`` values, in time order.
            branch2_scores: Branch 2's per-query anomaly score for each of
                ``texts`` (same order), if already computed (e.g. reused from
                ``data/processed/branch3_sessions_cach_a.csv`` during
                calibration/eval — avoids redundant recomputation). If
                ``None`` (the live-API path, where nothing is precomputed),
                computed here via ``self.b2_detector`` — still per query,
                NOT on the concatenated blob (see module docstring for why).

        Returns:
            Dict with ``attack_prob``, ``mean_score``, ``fraction_above``,
            ``fires_content``, ``fires_behavior``, ``is_attack``, and
            ``predicted_label`` (a specific Branch-1 class name if the content check
            fired, else ``"anomalous_session"`` if only behavior fired, else
            ``"benign"``).
        """
        from src.models.branch3_features import BRANCH1_LABEL_ORDER, branch1_probabilities, branch2_scores_for_texts
        from src.preprocessing.canonicalize import canonicalize

        canonical_texts = [canonicalize(t, self.max_decode_iterations).query_canonical for t in texts]
        concat_text = " ".join(canonical_texts)
        probs = branch1_probabilities([concat_text], self.b1_vectorizer, self.b1_clf)[0]
        attack_prob = 1.0 - probs[0]  # column 0 = "normal"
        fires_content = attack_prob >= self.content_threshold

        if branch2_scores is None:
            branch2_scores = branch2_scores_for_texts(canonical_texts, self.b2_detector)
        scores_arr = np.asarray(branch2_scores, dtype=np.float64)
        mean_score = float(scores_arr.mean())
        fraction_above = float((scores_arr > self.per_query_threshold).mean())
        fires_behavior = (mean_score >= self.mean_threshold) or (fraction_above >= self.fraction_threshold)

        if fires_content:
            from src.preprocessing.multiclass_tagger import LABEL_NAMES

            # Branch 1's OWN label schema (0=normal,1=union_based,2=error_based,
            # 3=boolean_blind,4=time_blind) — NOT the session-level schema in
            # self.class_names (0=benign,1=boolean_blind,2=time_blind,
            # 3=query_splitting). Same integers, different meaning; indexing
            # into the wrong one silently mislabels the attack type.
            top_class_id = BRANCH1_LABEL_ORDER[int(np.argmax(probs))]
            label = LABEL_NAMES.get(top_class_id, str(top_class_id))
        elif fires_behavior:
            label = "anomalous_session"
        else:
            label = "benign"

        return {
            "attack_prob": float(attack_prob),
            "mean_score": mean_score,
            "fraction_above": fraction_above,
            "fires_content": bool(fires_content),
            "fires_behavior": bool(fires_behavior),
            "is_attack": bool(fires_content or fires_behavior),
            "predicted_label": label,
        }

    def save(self, path: str | Path) -> None:
        """Persist only the calibrated thresholds — no model weights.

        Branch 1/Branch 2 artifacts are loaded separately by the caller
        (``deploy/registry.py``) and passed into ``__init__``; this just
        remembers which thresholds were calibrated.
        """
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        meta = {
            "mechanism": "session_correlator",
            "content_threshold": self.content_threshold,
            "per_query_threshold": self.per_query_threshold,
            "mean_threshold": self.mean_threshold,
            "fraction_threshold": self.fraction_threshold,
            "max_decode_iterations": self.max_decode_iterations,
        }
        with (path / "metadata.json").open("w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        logger.info("SessionCorrelator thresholds saved to %s", path)

    @classmethod
    def load(cls, path: str | Path, b1_vectorizer: Any, b1_clf: Any, b2_detector: Any) -> "SessionCorrelator":
        """Load calibrated thresholds and attach already-loaded B1/B2 artifacts."""
        path = Path(path)
        with (path / "metadata.json").open("r", encoding="utf-8") as f:
            meta = json.load(f)
        return cls(
            b1_vectorizer=b1_vectorizer,
            b1_clf=b1_clf,
            b2_detector=b2_detector,
            content_threshold=meta["content_threshold"],
            per_query_threshold=meta["per_query_threshold"],
            mean_threshold=meta["mean_threshold"],
            fraction_threshold=meta["fraction_threshold"],
            max_decode_iterations=meta.get("max_decode_iterations", 3),
        )

