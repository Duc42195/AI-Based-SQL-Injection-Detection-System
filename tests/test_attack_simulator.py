"""Tests for the real bisection attack driver (train/attack_simulator.py).

These run the actual bisection algorithm against the real deploy/demo_db.py
SQLite instance — the point is to verify the bisection math itself is
correct (it recovers the true seeded value), not just that the code runs.
"""

from __future__ import annotations

import random

from deploy import demo_db
from train.attack_simulator import (
    generate_synthetic_user_pool,
    run_benign_session,
    run_boolean_blind_session,
    run_time_blind_session,
)

_SEED_PASSWORDS = {row[1]: row[3] for row in demo_db._SEED_ROWS}  # username -> password


class TestBooleanBlindAttacker:
    def test_extracts_correct_prefix(self) -> None:
        rng = random.Random(1)
        steps, extracted = run_boolean_blind_session("admin", "password", rng, max_chars=4)
        assert extracted == _SEED_PASSWORDS["admin"][:4]

    def test_extracts_correct_prefix_for_different_user(self) -> None:
        rng = random.Random(2)
        steps, extracted = run_boolean_blind_session("bob", "password", rng, max_chars=5)
        assert extracted == _SEED_PASSWORDS["bob"][:5]

    def test_steps_contain_real_constructed_sql(self) -> None:
        rng = random.Random(3)
        steps, _ = run_boolean_blind_session("alice", "password", rng, max_chars=2)
        assert len(steps) > 0
        for step in steps:
            assert "SELECT * FROM users WHERE username" in step["query_raw"]
            assert step["timestamp"] > 0

    def test_step_count_matches_bisection_theory(self) -> None:
        # ~log2(24) for length + n_chars * log2(96) for ASCII range (31-127).
        rng = random.Random(4)
        steps, _ = run_boolean_blind_session("carol", "password", rng, max_chars=1)
        # length bisection (~5) + 1 char (~7) = roughly 10-14 steps
        assert 8 <= len(steps) <= 16


class TestTimeBlindAttacker:
    def test_extracts_correct_prefix(self) -> None:
        rng = random.Random(5)
        steps, extracted = run_time_blind_session("dave", "password", rng, max_chars=3, sleep_seconds=0.02)
        assert extracted == _SEED_PASSWORDS["dave"][:3]

    def test_true_steps_take_measurably_longer(self) -> None:
        # Re-run the underlying attacker directly to inspect per-probe timing.
        from train.attack_simulator import TimeBlindAttacker

        rng = random.Random(6)
        attacker = TimeBlindAttacker(rng, sleep_seconds=0.05)
        # A condition that's always true should take >= sleep_seconds.
        import time

        t0 = time.perf_counter()
        result_true = attacker._probe("1=1")
        elapsed_true = time.perf_counter() - t0

        t0 = time.perf_counter()
        result_false = attacker._probe("1=2")
        elapsed_false = time.perf_counter() - t0

        assert result_true is True
        assert result_false is False
        assert elapsed_true > elapsed_false
        assert elapsed_true >= 0.04  # close to sleep_seconds, allowing scheduler slack


class TestSyntheticUserPool:
    def test_generates_requested_count(self) -> None:
        rng = random.Random(10)
        pool = generate_synthetic_user_pool(20, rng)
        assert len(pool) == 20

    def test_usernames_and_passwords_are_distinct(self) -> None:
        rng = random.Random(11)
        pool = generate_synthetic_user_pool(50, rng)
        usernames = [row[1] for row in pool]
        passwords = [row[3] for row in pool]
        assert len(set(usernames)) == 50
        # Randomized passwords should (almost certainly) not collide either.
        assert len(set(passwords)) == 50

    def test_bisection_targets_the_synthetic_pool_not_the_live_demo(self) -> None:
        rng = random.Random(12)
        pool = generate_synthetic_user_pool(5, rng)
        _, target_username, _, target_password, _ = pool[0]
        steps, extracted = run_boolean_blind_session(
            target_username, "password", rng, max_chars=4, seed_rows=pool
        )
        assert extracted == target_password[:4]
        # Confirm this isn't accidentally hitting the live demo's fixed users.
        assert target_username not in demo_db.SEED_USERNAMES


class TestBenignSession:
    def test_returns_requested_step_count(self) -> None:
        rng = random.Random(7)
        steps = run_benign_session(rng, n_steps=6, gap_range=(1.0, 5.0))
        assert len(steps) == 6

    def test_uses_real_seeded_or_plausible_usernames(self) -> None:
        rng = random.Random(8)
        steps = run_benign_session(rng, n_steps=10, gap_range=(1.0, 5.0))
        for step in steps:
            assert "SELECT * FROM users WHERE username" in step["query_raw"]

    def test_timestamps_increase_monotonically(self) -> None:
        rng = random.Random(9)
        steps = run_benign_session(rng, n_steps=5, gap_range=(1.0, 5.0))
        timestamps = [s["timestamp"] for s in steps]
        assert timestamps == sorted(timestamps)
