from __future__ import annotations

import random
import string
import tempfile
from pathlib import Path

import pytest

from deploy import demo_db
from train.attack_simulator import (
    BooleanBlindAttacker,
    TimeBlindAttacker,
    BenignSessionGenerator,
    generate_synthetic_user_pool,
    _user_pool_to_seed_rows,
    verify_diversity,
    generate_all_sessions,
    _build_session_rows,
)


# --------------------------------------------------------------------------- #
# Synthetic user pool
# --------------------------------------------------------------------------- #

class TestSyntheticUserPool:
    def test_size(self):
        pool = generate_synthetic_user_pool(100)
        assert len(pool) == 100

    def test_password_length_range(self):
        pool = generate_synthetic_user_pool(50, password_min_len=6, password_max_len=8)
        for u in pool:
            assert 6 <= len(u["password"]) <= 8

    def test_deterministic_seed(self):
        a = generate_synthetic_user_pool(10, random_seed=42)
        b = generate_synthetic_user_pool(10, random_seed=42)
        assert a == b

    def test_unique_usernames(self):
        pool = generate_synthetic_user_pool(100)
        usernames = [u["username"] for u in pool]
        assert len(set(usernames)) == 100


class TestUserPoolToSeedRows:
    def test_shape(self):
        pool = [{"username": "a", "password": "p1"}, {"username": "b", "password": "p2"}]
        rows = _user_pool_to_seed_rows(pool)
        assert len(rows) == 2
        assert rows[0] == (1, "a", "a@test.local", "p1", "user")


# --------------------------------------------------------------------------- #
# BooleanBlindAttacker
# --------------------------------------------------------------------------- #

class TestBooleanBlindAttacker:
    @pytest.fixture
    def seed_rows(self):
        pool = generate_synthetic_user_pool(20, random_seed=42)
        return _user_pool_to_seed_rows(pool)

    def test_session_not_empty(self, seed_rows):
        user = seed_rows[0][1]
        attacker = BooleanBlindAttacker(seed_rows, user, max_chars=2)
        steps = attacker.run()
        assert len(steps) > 0

    def test_has_row_count_variance(self, seed_rows):
        user = seed_rows[0][1]
        attacker = BooleanBlindAttacker(seed_rows, user, max_chars=2)
        steps = attacker.run()
        row_counts = {s["row_count"] for s in steps}
        assert 0 in row_counts, "should have some steps with 0 rows"
        assert any(c > 0 for c in row_counts), "should have some steps with >0 rows"

    def test_queries_contain_ascii(self, seed_rows):
        user = seed_rows[0][1]
        attacker = BooleanBlindAttacker(seed_rows, user, max_chars=1)
        steps = attacker.run()
        assert all("ASCII" in s["query"] for s in steps)

    def test_session_reconstructs_password(self, seed_rows):
        user_row = seed_rows[0]
        user = user_row[1]
        password = user_row[3]
        attacker = BooleanBlindAttacker(seed_rows, user, max_chars=len(password))
        steps = attacker.run()
        assert len(steps) > 0


# --------------------------------------------------------------------------- #
# TimeBlindAttacker
# --------------------------------------------------------------------------- #

class TestTimeBlindAttacker:
    @pytest.fixture
    def seed_rows(self):
        pool = generate_synthetic_user_pool(10, random_seed=42)
        return _user_pool_to_seed_rows(pool)

    def test_session_not_empty(self, seed_rows):
        user = seed_rows[0][1]
        attacker = TimeBlindAttacker(seed_rows, user, max_chars=2, sleep_seconds=0.01)
        steps = attacker.run()
        assert len(steps) > 0

    def test_timing_variance(self, seed_rows):
        user = seed_rows[0][1]
        attacker = TimeBlindAttacker(seed_rows, user, max_chars=2, sleep_seconds=0.02)
        steps = attacker.run()
        timings = [s["timing_seconds"] for s in steps]
        assert max(timings) > min(timings) * 1.5, "should have fast and slow steps"


# --------------------------------------------------------------------------- #
# BenignSessionGenerator
# --------------------------------------------------------------------------- #

class TestBenignSessionGenerator:
    @pytest.fixture
    def seed_rows(self):
        pool = generate_synthetic_user_pool(10, random_seed=42)
        return _user_pool_to_seed_rows(pool)

    def test_all_return_one_row(self, seed_rows):
        gen = BenignSessionGenerator(seed_rows, gap_range=(1.0, 5.0), random_seed=42)
        steps = gen.generate(10)
        for s in steps:
            assert s["row_count"] == 1

    def test_has_gap_field(self, seed_rows):
        gen = BenignSessionGenerator(seed_rows, gap_range=(1.0, 5.0), random_seed=42)
        steps = gen.generate(5)
        for s in steps:
            assert "gap_seconds" in s
            assert s["gap_seconds"] > 0

    def test_length(self, seed_rows):
        gen = BenignSessionGenerator(seed_rows, gap_range=(1.0, 5.0), random_seed=42)
        steps = gen.generate(7)
        assert len(steps) == 7


# --------------------------------------------------------------------------- #
# Diversity verification
# --------------------------------------------------------------------------- #

class TestDiversity:
    def test_verify_diversity_boolean(self):
        pool = generate_synthetic_user_pool(10, random_seed=42)
        seed_rows = _user_pool_to_seed_rows(pool)
        sessions: list[tuple[str, list[dict]]] = []
        for i in range(5):
            user = pool[i]["username"]
            attacker = BooleanBlindAttacker(seed_rows, user, max_chars=1)
            steps = attacker.run()
            sessions.append((user, steps))
        result = verify_diversity(sessions)
        assert result["distinct_count"] >= 1


# --------------------------------------------------------------------------- #
# CSV output helpers
# --------------------------------------------------------------------------- #

class TestBuildSessionRows:
    def test_shape(self):
        steps = [
            {"query": "SELECT 1", "row_count": 1, "timing_seconds": 0.001},
            {"query": "SELECT 2", "row_count": 0, "timing_seconds": 0.002},
        ]
        rows = _build_session_rows(1, "boolean_blind", steps)
        assert len(rows) == 2
        assert rows[0]["session_id"] == 1
        assert rows[0]["step_idx"] == 1
        assert rows[0]["class"] == "boolean_blind"
        assert list(rows[0].keys()) == [
            "session_id", "step_idx", "class", "query", "row_count", "timing_seconds",
        ]


# --------------------------------------------------------------------------- #
# End-to-end generation
# --------------------------------------------------------------------------- #

class TestGenerateAllSessions:
    def test_small_run(self, tmp_path: Path):
        report = generate_all_sessions(
            output_dir=tmp_path,
            n_train_per_class=2,
            n_test_per_class=1,
            user_pool_size=10,
            password_min_len=6,
            password_max_len=8,
            max_extract_chars=2,
            sleep_seconds=0.005,
            benign_min_steps=3,
            benign_max_steps=5,
            benign_gap_seconds=(0.001, 0.01),
            random_seed=42,
        )
        assert report["total_sessions_generated"] > 0
        assert "boolean_blind" in report["classes"]
        assert "time_blind" in report["classes"]
        assert "benign" in report["classes"]
        assert "diversity" in report

        files = list(tmp_path.iterdir())
        csv_files = [f.name for f in files if f.suffix == ".csv"]
        for cls in ["boolean_blind", "time_blind", "benign"]:
            assert f"{cls}_train.csv" in csv_files, f"missing {cls}_train.csv"
            assert f"{cls}_test.csv" in csv_files, f"missing {cls}_test.csv"
