"""Build the Branch 3 (session-level) training dataset — Cách A.

Four session types, matching `branch3_session.session_classes` in
configs/config.yaml:

  - benign (0): real legitimate lookups against the real demo DB.
  - boolean_blind (1) / time_blind (2): a REAL bisection extraction attack
    (see train/attack_simulator.py) run against `deploy/demo_db.py` — actual
    SQL executed by SQLite, real row-count/timing oracle, not a guessed
    approximation. This replaced an earlier version that sampled unrelated
    real attack payloads i.i.d., which produced a misleadingly easy dataset
    (Branch 1 already recognizes those payloads per-query, so the session
    model's job reduced to "aggregate an already-correct signal" — not a
    test of anything). See data_contract.md Section 4.1 for the full story.
  - query_splitting (3): synthesized by fragmenting ONE real attack payload
    into 2-4 pieces at token boundaries, each sent as a separate step. No
    per-query "query_splitting" label exists anywhere in the source data
    (splitting is inherently a multi-request pattern), and the demo DB has
    only one injectable parameter (nothing to realistically probe across),
    so this one session type stays on the heuristic fragmentation approach.

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
from src.models.branch3_features import (
    BRANCH1_LABEL_ORDER,
    branch1_prob_columns,
    branch1_probabilities,
    branch2_scores_for_texts,
)
from src.utils import Config, get_logger, load_config
from attack_simulator import (
    generate_synthetic_user_pool,
    run_benign_session,
    run_boolean_blind_session,
    run_time_blind_session,
)

logger = get_logger(__name__)


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


def _assemble_rows(
    session_id: str, session_label: int, session_source: str, steps: list[dict], split: str
) -> list[dict]:
    """Turn a raw step list (query_raw/query_canonical/timestamp) into full rows.

    ``gap_seconds`` (0.0 for the first step) is computed from REAL consecutive
    timestamps for real-DB-driven sessions — for time-blind sessions this
    directly reflects genuine measured SLEEP delays, not a guessed range.

    ``split`` is decided by the caller at generation time (not by shuffling
    session IDs afterwards) — see the leakage note in ``build_sessions``.
    """
    rows = []
    prev_ts = None
    for step_index, step in enumerate(steps):
        ts = step["timestamp"]
        gap = 0.0 if prev_ts is None else ts - prev_ts
        rows.append(
            {
                "session_id": session_id,
                "step_index": step_index,
                "query_raw": step["query_raw"],
                "query_canonical": step["query_canonical"],
                "timestamp": ts,
                "gap_seconds": round(gap, 6),
                "session_label": session_label,
                "session_source": session_source,
                "split": split,
            }
        )
        prev_ts = ts
    return rows


def _sample_targets(pool: list[str], n: int, rng: random.Random) -> list[str]:
    """Draw ``n`` usernames from ``pool``, using every entry once before repeating."""
    if n <= len(pool):
        return rng.sample(pool, n)
    usernames = list(pool)
    rng.shuffle(usernames)
    usernames += rng.choices(pool, k=n - len(pool))
    return usernames


def build_sessions(cfg: Config, df_train: pd.DataFrame, rng: random.Random) -> list[dict]:
    """Generate all Cách A session rows (without Branch 1/2 scores yet).

    Train/test membership is decided PER SESSION at generation time, not by
    shuffling session IDs after the fact (see the pool-partition note below
    for why that used to leak).
    """
    cach_a = cfg.get_path("branch3_session.cach_a")
    n_per_class = int(cach_a["sessions_per_class"])
    attack_gap = tuple(cach_a["attack_step_gap_seconds"])
    frag_min, frag_max = cach_a["splitting_fragments"]
    benign_min_steps, benign_max_steps = int(cach_a["min_len"]), int(cach_a["max_len"])
    benign_gap = tuple(cach_a["benign_step_gap_seconds"])
    test_fraction = float(cach_a.get("test_fraction", 0.2))
    n_test = max(1, round(n_per_class * test_fraction))
    n_train = n_per_class - n_test

    real_db_cfg = cach_a["real_db"]
    target_column = real_db_cfg["target_column"]
    max_extract_chars = int(real_db_cfg["max_extract_chars"])
    time_blind_sleep = float(real_db_cfg["time_blind_sleep_seconds"])
    n_synthetic_users = int(real_db_cfg["synthetic_user_pool_size"])

    # A larger, randomized user pool for training-data generation ONLY — the
    # bisection algorithm is deterministic given a target value, so attacking
    # the live demo's fixed 5 users would produce only 5 distinct traces no
    # matter how many "sessions" are requested (confirmed: 350 sessions over
    # 5 users repeated every trace ~70x — the model was memorizing, not
    # generalizing). deploy/demo_db.py's own 5-row table is untouched.
    user_pool = generate_synthetic_user_pool(n_synthetic_users, rng)
    pool_usernames = [row[1] for row in user_pool]
    logger.info("Generated a %d-user synthetic pool for training-data diversity", n_synthetic_users)

    # boolean_blind/time_blind: the SAME target username always produces a
    # byte-identical trace (deterministic bisection). A big pool only
    # protects against duplicates WITHIN one split — it does nothing to stop
    # a target from landing in BOTH splits, which is what actually leaked
    # (audit: 65/70 boolean_blind and 67/70 time_blind TEST sessions were
    # byte-identical to a TRAIN session). Fix: partition the pool into
    # disjoint train/test subsets BEFORE assigning targets, so no username
    # can ever be sampled for both splits.
    shuffled_pool = list(pool_usernames)
    rng.shuffle(shuffled_pool)
    n_test_users = max(1, round(len(shuffled_pool) * test_fraction))
    test_pool_usernames = shuffled_pool[:n_test_users]
    train_pool_usernames = shuffled_pool[n_test_users:]

    rows: list[dict] = []

    # benign (0) — real lookups against the larger real DB pool. Each step
    # picks its username independently at random (not one fixed target for
    # the whole session), so this isn't target-deterministic and a plain
    # per-session split is safe.
    logger.info("Generating %d benign sessions (real DB lookups) ...", n_per_class)
    benign_split = ["train"] * n_train + ["test"] * n_test
    rng.shuffle(benign_split)
    for i in range(n_per_class):
        n_steps = rng.randint(benign_min_steps, benign_max_steps)
        steps = run_benign_session(rng, n_steps, benign_gap, seed_rows=user_pool)
        rows += _assemble_rows(f"cachA_benign_{i:04d}", 0, "A_real_db", steps, benign_split[i])

    # boolean_blind (1) — real bisection attack; targets drawn from
    # split-exclusive user subsets so TRAIN and TEST never share a target.
    logger.info(
        "Generating %d boolean_blind sessions (real bisection attack, %d train / %d test targets) ...",
        n_per_class, n_train, n_test,
    )
    for i, username in enumerate(_sample_targets(train_pool_usernames, n_train, rng)):
        steps, extracted = run_boolean_blind_session(
            username, target_column, rng, max_extract_chars, seed_rows=user_pool
        )
        rows += _assemble_rows(f"cachA_boolean_blind_train_{i:04d}", 1, "A_real_db", steps, "train")
    for i, username in enumerate(_sample_targets(test_pool_usernames, n_test, rng)):
        steps, extracted = run_boolean_blind_session(
            username, target_column, rng, max_extract_chars, seed_rows=user_pool
        )
        rows += _assemble_rows(f"cachA_boolean_blind_test_{i:04d}", 1, "A_real_db", steps, "test")

    # time_blind (2) — same real bisection, oracle = real measured timing.
    logger.info(
        "Generating %d time_blind sessions (real timing attack, %d train / %d test targets) ...",
        n_per_class, n_train, n_test,
    )
    for i, username in enumerate(_sample_targets(train_pool_usernames, n_train, rng)):
        steps, extracted = run_time_blind_session(
            username, target_column, rng, max_extract_chars,
            sleep_seconds=time_blind_sleep, seed_rows=user_pool,
        )
        rows += _assemble_rows(f"cachA_time_blind_train_{i:04d}", 2, "A_real_db", steps, "train")
    for i, username in enumerate(_sample_targets(test_pool_usernames, n_test, rng)):
        steps, extracted = run_time_blind_session(
            username, target_column, rng, max_extract_chars,
            sleep_seconds=time_blind_sleep, seed_rows=user_pool,
        )
        rows += _assemble_rows(f"cachA_time_blind_test_{i:04d}", 2, "A_real_db", steps, "test")

    # query_splitting (3) — unchanged: fragment one real attack payload. Not
    # target-deterministic (random source payload + random fragmentation
    # cuts each draw), so a plain per-session split is safe. No second
    # vulnerable parameter exists in the demo DB to realistically probe
    # across, and no per-query "splitting" label exists in any source data,
    # so generation itself stays on the heuristic approach (data_contract.md).
    logger.info("Generating %d query_splitting sessions (fragmentation heuristic) ...", n_per_class)
    by_label = {
        name: df_train.loc[df_train["label_name"] == name, "query_canonical"].tolist()
        for name in ("union_based", "error_based", "boolean_blind", "time_blind")
    }
    all_attack_texts = by_label["union_based"] + by_label["error_based"] + by_label["boolean_blind"] + by_label["time_blind"]
    base_ts = time.time() - 86400 * 30
    splitting_split = ["train"] * n_train + ["test"] * n_test
    rng.shuffle(splitting_split)
    for i in range(n_per_class):
        source_text = rng.choice(all_attack_texts)
        n_frag = rng.randint(int(frag_min), int(frag_max))
        texts = _fragment_text(source_text, n_frag, rng)
        steps = []
        ts = base_ts + rng.uniform(0, 86400 * 30)
        for text in texts:
            steps.append({"query_raw": text, "query_canonical": text, "timestamp": ts})
            ts += rng.uniform(*attack_gap)
        rows += _assemble_rows(f"cachA_query_splitting_{i:04d}", 3, "A_simulated", steps, splitting_split[i])

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
    logger.info("Loaded %d Branch-1 train rows (used only for query_splitting fragments)", len(df_train))

    logger.info("Generating Cách A sessions ...")
    rows = build_sessions(cfg, df_train, rng)
    logger.info("Generated %d rows across %d sessions", len(rows), len({r["session_id"] for r in rows}))

    vectorizer, clf = _load_branch1(models_dir, cfg.get_path("branch1_supervised.active_version", "branch1_v1"))
    detector = _load_branch2(models_dir, cfg.get_path("branch2_anomaly.active_version", "branch2_v1"))
    feature_names = list(
        cfg.get_path("branch2_anomaly.features", [
            "length", "special_char_ratio", "sql_keyword_count", "entropy",
            "bigram_entropy", "quote_imbalance", "same_type_run_ratio",
            "max_token_length", "token_count", "max_special_run",
            "max_digit_run", "paren_imbalance",
        ])
    )

    logger.info("Running Branch 1 + Branch 2 inference on every step ...")
    texts = [r["query_canonical"] for r in rows]
    probs = branch1_probabilities(texts, vectorizer, clf)
    scores = branch2_scores_for_texts(texts, detector, feature_names)

    prob_cols = branch1_prob_columns()
    for i, r in enumerate(rows):
        r["branch1_label"] = int(BRANCH1_LABEL_ORDER[int(np.argmax(probs[i]))])
        for col, name in enumerate(prob_cols):
            r[name] = round(float(probs[i, col]), 6)
        r["branch2_anomaly_score"] = round(float(scores[i]), 6)

    out_df = pd.DataFrame(rows)

    # `split` was already decided per session at generation time (see
    # build_sessions) so that boolean_blind/time_blind targets never
    # straddle both splits — nothing to compute here, just report it.
    session_meta = out_df.drop_duplicates("session_id")[["session_id", "session_label", "split"]]

    out_cols = (
        ["session_id", "step_index", "query_raw", "query_canonical", "branch1_label"]
        + prob_cols
        + ["branch2_anomaly_score", "gap_seconds", "timestamp", "session_label", "session_source", "split"]
    )
    out_df = out_df[out_cols]

    out_path = processed_dir / "branch3_sessions_cach_a.csv"
    out_df.to_csv(out_path, index=False)

    n_sessions = out_df["session_id"].nunique()
    n_train_sessions = int((session_meta["split"] == "train").sum())
    n_test_sessions = int((session_meta["split"] == "test").sum())
    logger.info(
        "Saved %d rows / %d sessions to %s (train sessions=%d, test sessions=%d)",
        len(out_df), n_sessions, out_path, n_train_sessions, n_test_sessions,
    )
    logger.info("Session-label distribution:\n%s", session_meta["session_label"].value_counts().sort_index())


if __name__ == "__main__":
    main()
