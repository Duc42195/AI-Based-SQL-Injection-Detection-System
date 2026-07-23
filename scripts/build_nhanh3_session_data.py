"""Build Cach A session data for Branch 3 by simulating sessions from D1 queries."""
from __future__ import annotations

import csv
import random
import urllib.parse
from pathlib import Path

from datasets import load_dataset

from src.preprocessing.statistical_features import extract_statistical_features
from src.utils import get_logger, load_config

logger = get_logger(__name__)


def _sample_range(rng, lo, hi):
    return rng.randint(lo, hi)


def _sample_seq(rng, pool, n):
    return [rng.choice(pool) for _ in range(n)]


def _build_rows(steps, sid, slabel, sname, split):
    rows = []
    for si, s in enumerate(steps):
        f = extract_statistical_features(s["query_canonical"])
        rows.append({
            "session_id": sid, "step": si, "split": split,
            "query_raw": s["query_raw"], "query_canonical": s["query_canonical"],
            "has_comment_marker": int(s["has_comment_marker"]),
            "length": f.length, "special_char_ratio": round(f.special_char_ratio, 6),
            "sql_keyword_count": f.sql_keyword_count, "entropy": round(f.entropy, 6),
            "is_attack_query": 1 if s["label"] != 0 else 0,
            "per_query_label": s["label"], "per_query_label_name": s["label_name"],
            "session_label": slabel, "session_label_name": sname,
        })
    return rows


def _gen_benign(rng, pool, sid, mn, mx, split, noise_frac=0.0, noise_pool=None):
    """Generate benign session, with probability-based attack noise."""
    n = _sample_range(rng, mn, mx)
    steps = _sample_seq(rng, pool, n)
    if noise_frac > 0 and noise_pool:
        # Per-query noise probability (not per-session)
        for i in range(n):
            if rng.random() < noise_frac:
                steps[i] = rng.choice(noise_pool)
    return _build_rows(steps, sid, 0, "benign", split)


def _gen_blind_interleaved(rng, npool, apool, sid, alabel, aname,
                            n_attacks_range, normal_between_prob, split):
    """Generate blind session with interleaved normals between attacks.
    Produces realistic attack_ratio (0.3-0.7) by scattering normals
    between attack queries instead of grouping them all together.
    """
    n_attacks = _sample_range(rng, *n_attacks_range)
    steps = []
    n_lead = rng.randint(1, 2)
    steps.extend(_sample_seq(rng, npool, n_lead))
    for ai in range(n_attacks):
        steps.append(rng.choice(apool))
        if rng.random() < normal_between_prob:
            steps.append(rng.choice(npool))
        if ai == n_attacks // 2 and rng.random() < 0.5:
            steps.append(rng.choice(npool))
    n_trail = rng.randint(0, 1)
    steps.extend(_sample_seq(rng, npool, n_trail))
    return _build_rows(steps, sid, alabel, aname, split)


def _gen_split(rng, npool, apool, sid, split):
    """Generate query-splitting session with camouflaged fragments."""
    long = [a for a in apool if len(a["query_canonical"]) >= 60] or apool
    base = rng.choice(long)
    parts = base["query_canonical"].split()
    if len(parts) < 3:
        return _build_rows(_sample_seq(rng, npool, 2) + [base], sid, 3, "query_splitting", split)
    sp = [len(parts) // 3, 2 * len(parts) // 3]
    frags = [" ".join(parts[:sp[0]]), " ".join(parts[sp[0]:sp[1]]), " ".join(parts[sp[1]:])]

    # URL-encode fragments and add benign-looking params to evade simple detection
    def _camouflage(text):
        encoded = urllib.parse.quote(text, safe="=?&%/")
        if rng.random() < 0.5:
            encoded += "&utm_source=webapp&_=" + str(rng.randint(100000, 999999))
        return encoded

    steps = _sample_seq(rng, npool, _sample_range(rng, 1, 2)) + [
        {"query_raw": f, "query_canonical": _camouflage(f),
         "has_comment_marker": 0, "label": 0, "label_name": "normal"}
        for f in frags[:2]
    ] + _sample_seq(rng, npool, _sample_range(rng, 0, 1)) + [
        {"query_raw": frags[2], "query_canonical": _camouflage(frags[2]),
         "has_comment_marker": 0,
         "label": base["label"], "label_name": base["label_name"]},
    ] + _sample_seq(rng, npool, _sample_range(rng, 0, 1))
    return _build_rows(steps, sid, 3, "query_splitting", split)


def main():
    cfg = load_config()
    rng = random.Random(cfg.get_path("branch3_session.simulation.seed", 42))
    pd_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    pd_dir.mkdir(parents=True, exist_ok=True)

    n = cfg.get_path("branch3_session.simulation.num_sessions_per_class", 5000)
    tf = cfg.get_path("branch3_session.simulation.test_fraction", 0.2)
    bc = cfg.get_path("branch3_session.simulation.benign", {})
    dlc = cfg.get_path("branch3_session.simulation.blind", {})

    ds = load_dataset("Jason-42195/VNU-SQLi-Detection", data_files="nhanh1_train.csv", split="train")
    logger.info("Loaded %d rows", len(ds))

    pools = {0: [], 3: [], 4: [], "other": []}
    for r in ds:
        e = {"query_raw": r["query_raw"], "query_canonical": r["query_canonical"],
             "has_comment_marker": r["has_comment_marker"], "label": r["label"],
             "label_name": r["label_name"]}
        pools.get(r["label"] if r["label"] in (0, 3, 4) else "other", []).append(e)

    logger.info("Pools: normal=%d bb=%d tb=%d other=%d",
                len(pools[0]), len(pools[3]), len(pools[4]), len(pools["other"]))

    nb_prob = dlc.get("normal_between_prob", 0.3)
    n_attacks = dlc.get("attack_queries", [2, 8])
    noise_frac = bc.get("noise_fraction", 0.0)
    attack_pool = pools[3] + pools[4] + pools["other"]

    all_rows = []
    sid = 0

    for _ in range(n):
        sp = "test" if rng.random() < tf else "train"
        all_rows.extend(_gen_benign(rng, pools[0], sid, bc.get("min_len", 3), bc.get("max_len", 15),
                                     sp, noise_frac, attack_pool if noise_frac > 0 else None))
        sid += 1

    if pools[3]:
        for _ in range(n):
            sp = "test" if rng.random() < tf else "train"
            all_rows.extend(_gen_blind_interleaved(rng, pools[0], pools[3], sid,
                                                   1, "boolean_blind", n_attacks, nb_prob, sp))
            sid += 1

    if pools[4]:
        for _ in range(n):
            sp = "test" if rng.random() < tf else "train"
            all_rows.extend(_gen_blind_interleaved(rng, pools[0], pools[4], sid,
                                                   2, "time_blind", n_attacks, nb_prob, sp))
            sid += 1

    if attack_pool:
        for _ in range(n):
            sp = "test" if rng.random() < tf else "train"
            all_rows.extend(_gen_split(rng, pools[0], attack_pool, sid, sp))
            sid += 1

    out = pd_dir / "nhanh3_session_data.csv"
    fnames = ["session_id", "step", "split", "query_raw", "query_canonical", "has_comment_marker",
              "length", "special_char_ratio", "sql_keyword_count", "entropy",
              "is_attack_query", "per_query_label", "per_query_label_name",
              "session_label", "session_label_name"]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fnames)
        w.writeheader()
        w.writerows(all_rows)
    logger.info("Saved %d step-rows (%d sessions) to %s", len(all_rows), sid, out)


if __name__ == "__main__":
    main()
