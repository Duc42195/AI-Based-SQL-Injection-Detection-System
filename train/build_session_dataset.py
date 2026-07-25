"""Build the Branch 3 (session-level) training dataset — Cách A (simulated).

Cách A builds sessions from EXISTING Branch 1 labeled queries rather than
real captured traffic (that's Cách B: sqlmap against a Docker lab, not done
yet — see data_contract.md). Four session types, matching
`branch3_session.session_classes` in configs/config.yaml:

  - benign (0): a run of unrelated `normal`-labeled queries.
  - boolean_blind (1) / time_blind (2): a run of real per-query attack
    payloads of that type, simulating a scripted probing sequence (e.g.
    sqlmap's binary-search boolean-blind extraction, or repeated
    SLEEP()-based timing probes).
  - query_splitting (3): synthesized by fragmenting ONE real attack payload
    into 2-4 pieces, each sent as a separate step. No per-query
    "query_splitting" label exists anywhere in the source data (splitting is
    inherently a multi-request pattern), so this is the one session type
    that can't be built by sampling — it has to be constructed.

Per-step model input = Branch 1's 5-class probability vector concatenated
with Branch 2's anomaly score. Both are computed here by loading the actual
trained branch1_v1 / branch2_v1 models and running real inference on every
step's query_canonical — including on query_splitting's synthetic fragments,
which is the point: a fragment alone often still looks benign to Branch 1,
exactly the gap Branch 3 exists to close.
"""

from __future__ import annotations

import random
import re
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.models.branch2_anomaly import AnomalyDetector
from src.preprocessing.multiclass_tagger import LABEL_NAMES
from src.preprocessing.statistical_features import extract_statistical_features
from src.utils import Config, get_logger, load_config

logger = get_logger(__name__)

# Branch 1 label ids (from configs/config.yaml: labels.classes), fixed order
# for the probability-vector columns written to the output CSV.
_BRANCH1_LABEL_ORDER = [0, 1, 2, 3, 4]  # normal, union_based, error_based, boolean_blind, time_blind


def _load_branch1(models_dir: Path, version: str) -> tuple:
    """Load the Branch 1 vectorizer + classifier."""
    model_dir = models_dir / version
    vectorizer = joblib.load(model_dir / "vectorizer.joblib")
    clf = joblib.load(model_dir / "model.joblib")
    logger.info("Loaded Branch 1 model from %s", model_dir)
    return vectorizer, clf


def _load_branch2(models_dir: Path, version: str) -> AnomalyDetector:
    """Load the Branch 2 anomaly detector."""
    detector = AnomalyDetector.load(models_dir / version)
    logger.info("Loaded Branch 2 model from %s", models_dir / version)
    return detector


def _branch1_probabilities(
    texts: list[str], vectorizer, clf
) -> np.ndarray:
    """Run Branch 1 inference, returning a (n, 5) probability matrix.

    Columns follow ``_BRANCH1_LABEL_ORDER``. The classifier only knows the
    classes present at its own training time (`stacked` was excluded), so we
    map from ``clf.classes_`` rather than assuming a fixed column order.
    """
    probs = clf.predict_proba(vectorizer.transform(texts))
    classes = [int(c) for c in clf.classes_]
    out = np.zeros((len(texts), len(_BRANCH1_LABEL_ORDER)), dtype=np.float64)
    for col, label in enumerate(_BRANCH1_LABEL_ORDER):
        if label in classes:
            out[:, col] = probs[:, classes.index(label)]
    return out


def _branch2_scores(texts: list[str], detector: AnomalyDetector, feature_names: list[str]) -> np.ndarray:
    """Run Branch 2 inference, returning a (n,) anomaly-score vector."""
    X = np.array(
        [extract_statistical_features(t).as_list() for t in texts], dtype=np.float64
    )
    # extract_statistical_features always returns [length, special_char_ratio,
    # sql_keyword_count, entropy] in that order, matching the default feature
    # set — reorder only if config specifies a different order.
    default_order = ["length", "special_char_ratio", "sql_keyword_count", "entropy"]
    if feature_names != default_order:
        idx = [default_order.index(f) for f in feature_names]
        X = X[:, idx]
    return detector.score(X)


_TOKEN_BOUNDARY_RE = re.compile(r"\s+|(?<=[(),;])|(?=[(),;])")


def _fragment_text(text: str, n_fragments: int, rng: random.Random) -> list[str]:
    """Split ``text`` into ``n_fragments`` pieces at token/punctuation boundaries.

    Splitting at raw character offsets produces garbled, non-SQL-looking
    substrings (e.g. cutting mid-keyword) that don't resemble how a real
    query-splitting attack would actually be staged across requests. Instead
    this splits at whitespace/punctuation boundaries so each fragment reads
    as a plausible (if incomplete) piece of syntax — e.g. `"1) UNION"` /
    `"SELECT password"` / `"FROM users--"` rather than `"1) UNIO"` / `"N SELE"`.
    """
    tokens = [t for t in _TOKEN_BOUNDARY_RE.split(text) if t and not t.isspace()]
    if len(tokens) <= 1:
        return [text]
    n_fragments = min(n_fragments, len(tokens))
    if n_fragments <= 1:
        return [text]
    # Distribute tokens across n_fragments contiguous, roughly-equal chunks.
    base = len(tokens) / n_fragments
    cuts = sorted(
        {
            max(1, min(len(tokens) - 1, round(base * i + rng.uniform(-base * 0.2, base * 0.2))))
            for i in range(1, n_fragments)
        }
    )
    pieces = []
    start = 0
    for c in cuts:
        pieces.append(" ".join(tokens[start:c]))
        start = c
    pieces.append(" ".join(tokens[start:]))
    return [p for p in pieces if p]


def _build_session_rows(
    session_id: str,
    session_label: int,
    texts: list[str],
    start_ts: float,
    gap_range: tuple[float, float],
    session_source: str,
    rng: random.Random,
) -> list[dict]:
    """Assemble the row dicts for one session (probabilities/scores filled in later).

    ``gap_seconds`` (0.0 for the first step) is a real temporal signal that
    per-query classifiers structurally cannot see — scripted attack probing
    (boolean/time-blind, query-splitting) uses tight, uniform gaps while
    benign browsing is slower and more irregular. It's a first-class feature
    for the sequence model, not just metadata.
    """
    rows = []
    ts = start_ts
    gap = 0.0
    for step, text in enumerate(texts):
        rows.append(
            {
                "session_id": session_id,
                "step_index": step,
                "query_raw": text,
                "query_canonical": text,  # source queries are already canonicalized
                "timestamp": ts,
                "gap_seconds": round(gap, 3),
                "session_label": session_label,
                "session_source": session_source,
            }
        )
        gap = rng.uniform(*gap_range)
        ts += gap
    return rows


def build_sessions(cfg: Config, df_train: pd.DataFrame, rng: random.Random) -> list[dict]:
    """Generate all Cách A session rows (without Branch 1/2 scores yet)."""
    cach_a = cfg.get_path("branch3_session.cach_a")
    n_per_class = int(cach_a["sessions_per_class"])
    min_len, max_len = int(cach_a["min_len"]), int(cach_a["max_len"])
    benign_gap = tuple(cach_a["benign_step_gap_seconds"])
    attack_gap = tuple(cach_a["attack_step_gap_seconds"])
    frag_min, frag_max = cach_a["splitting_fragments"]

    by_label = {
        name: df_train.loc[df_train["label_name"] == name, "query_canonical"].tolist()
        for name in ("normal", "union_based", "error_based", "boolean_blind", "time_blind")
    }
    all_attack_texts = by_label["union_based"] + by_label["error_based"] + by_label["boolean_blind"] + by_label["time_blind"]

    base_ts = time.time() - 86400 * 30  # spread sessions over the last ~30 days
    rows: list[dict] = []

    # benign (0)
    for i in range(n_per_class):
        n_steps = rng.randint(min_len, max_len)
        texts = rng.sample(by_label["normal"], n_steps)
        rows += _build_session_rows(
            f"cachA_benign_{i:04d}", 0, texts,
            base_ts + rng.uniform(0, 86400 * 30), benign_gap, "A_simulated", rng,
        )

    # boolean_blind (1) / time_blind (2): a run of real per-query attacks of
    # that type, simulating scripted probing. Optionally prefixed with 0-2
    # benign "recon" queries, which is realistic and also stresses the model
    # to not just key off "first query is an attack".
    for label_name, session_label in (("boolean_blind", 1), ("time_blind", 2)):
        for i in range(n_per_class):
            n_steps = rng.randint(min_len, max_len)
            n_lead_in = rng.randint(0, min(2, n_steps - 1))
            texts = rng.sample(by_label["normal"], n_lead_in)
            texts += rng.sample(by_label[label_name], n_steps - n_lead_in)
            rows += _build_session_rows(
                f"cachA_{label_name}_{i:04d}", session_label, texts,
                base_ts + rng.uniform(0, 86400 * 30), attack_gap, "A_simulated", rng,
            )

    # query_splitting (3): fragment one real attack payload into pieces.
    for i in range(n_per_class):
        source_text = rng.choice(all_attack_texts)
        n_frag = rng.randint(int(frag_min), int(frag_max))
        texts = _fragment_text(source_text, n_frag, rng)
        rows += _build_session_rows(
            f"cachA_query_splitting_{i:04d}", 3, texts,
            base_ts + rng.uniform(0, 86400 * 30), attack_gap, "A_simulated", rng,
        )

    return rows


def main() -> None:
    cfg = load_config()
    seed = int(cfg.get_path("project.random_seed", 42))
    rng = random.Random(seed)

    models_dir = Path(cfg.get_path("paths.models_dir", "models"))
    processed_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))

    branch1_path = processed_dir / "branch1_train.csv"
    if not branch1_path.exists():
        raise FileNotFoundError(f"{branch1_path} not found. Run train/build_branch1_dataset.py first.")
    df = pd.read_csv(branch1_path)
    df_train = df[df["split"] == "train"].reset_index(drop=True)
    logger.info("Loaded %d Branch-1 train rows to sample sessions from", len(df_train))

    logger.info("Generating Cách A sessions ...")
    rows = build_sessions(cfg, df_train, rng)
    logger.info("Generated %d rows across %d sessions", len(rows), len({r["session_id"] for r in rows}))

    vectorizer, clf = _load_branch1(models_dir, cfg.get_path("branch1_supervised.active_version", "branch1_v1"))
    detector = _load_branch2(models_dir, cfg.get_path("branch2_anomaly.active_version", "branch2_v1"))
    feature_names = list(
        cfg.get_path("branch2_anomaly.features", ["length", "special_char_ratio", "sql_keyword_count", "entropy"])
    )

    logger.info("Running Branch 1 + Branch 2 inference on every step ...")
    texts = [r["query_canonical"] for r in rows]
    probs = _branch1_probabilities(texts, vectorizer, clf)
    scores = _branch2_scores(texts, detector, feature_names)

    prob_cols = [f"branch1_prob_{LABEL_NAMES[label]}" for label in _BRANCH1_LABEL_ORDER]
    for i, r in enumerate(rows):
        r["branch1_label"] = int(_BRANCH1_LABEL_ORDER[int(np.argmax(probs[i]))])
        for col, name in enumerate(prob_cols):
            r[name] = round(float(probs[i, col]), 6)
        r["branch2_anomaly_score"] = round(float(scores[i]), 6)

    out_df = pd.DataFrame(rows)

    # Train/test split at the SESSION level (not row level), stratified by
    # session_label, so a session's steps never straddle both splits.
    test_fraction = float(cfg.get_path("branch3_session.cach_a.test_fraction", 0.2))
    session_meta = out_df.drop_duplicates("session_id")[["session_id", "session_label"]]
    test_ids: set[str] = set()
    for label in session_meta["session_label"].unique():
        ids = session_meta.loc[session_meta["session_label"] == label, "session_id"].tolist()
        rng.shuffle(ids)
        n_test = max(1, int(len(ids) * test_fraction))
        test_ids.update(ids[:n_test])
    out_df["split"] = out_df["session_id"].apply(lambda sid: "test" if sid in test_ids else "train")

    out_cols = (
        ["session_id", "step_index", "query_raw", "query_canonical", "branch1_label"]
        + prob_cols
        + ["branch2_anomaly_score", "gap_seconds", "timestamp", "session_label", "session_source", "split"]
    )
    out_df = out_df[out_cols]

    out_path = processed_dir / "branch3_sessions_cach_a.csv"
    out_df.to_csv(out_path, index=False)

    n_sessions = out_df["session_id"].nunique()
    n_train_sessions = session_meta.loc[~session_meta["session_id"].isin(test_ids)].shape[0]
    logger.info(
        "Saved %d rows / %d sessions to %s (train sessions=%d, test sessions=%d)",
        len(out_df), n_sessions, out_path, n_train_sessions, len(test_ids),
    )
    logger.info("Session-label distribution:\n%s", session_meta["session_label"].value_counts().sort_index())


if __name__ == "__main__":
    main()
