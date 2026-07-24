"""Intentionally-vulnerable demo database for the Test page.

PURPOSE (defensive/education only): show that a SQLi payload succeeds when there
is NO model in front of the DB, and is blocked when the detector is enabled. It
is a throwaway in-memory SQLite seeded with FAKE data — never wire real data or
a real DB to this module.

The vulnerability is deliberate: the query is built by *string concatenation*
(``... WHERE username = '<input>'``) exactly like a naive backend at "Vị trí B",
so classic payloads like ``' OR '1'='1`` change the query's meaning.
"""

from __future__ import annotations

import sqlite3
from threading import Lock
from typing import Any

from src.utils import get_logger

logger = get_logger(__name__)

TABLE = "users"
COLUMNS = ["id", "username", "email", "password", "role"]
# The naive backend template — user input is concatenated in unsanitised.
QUERY_TEMPLATE = "SELECT * FROM users WHERE username = '{input}'"

# Fake seed data. A normal single-user lookup returns exactly one row; an
# injection that returns more than one row is flagged as a data leak.
_SEED_ROWS: list[tuple[int, str, str, str, str]] = [
    (1, "admin", "admin@corp.vn", "S3cr3t!Adm", "admin"),
    (2, "alice", "alice@corp.vn", "aliceP@ss1", "user"),
    (3, "bob", "bob@corp.vn", "bobData123", "user"),
    (4, "carol", "carol@corp.vn", "carol!2026", "user"),
    (5, "dave", "dave@corp.vn", "daveVNU_db", "user"),
]

_lock = Lock()


def _fresh_connection() -> sqlite3.Connection:
    """Create a throwaway in-memory SQLite seeded with the fake users table."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, "
        "email TEXT, password TEXT, role TEXT)"
    )
    conn.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?)", _SEED_ROWS)
    conn.commit()
    return conn


def get_table() -> dict[str, Any]:
    """Return the seeded demo table for display on the Test page."""
    return {
        "table": TABLE,
        "columns": COLUMNS,
        "rows": [dict(zip(COLUMNS, row)) for row in _SEED_ROWS],
        "row_count": len(_SEED_ROWS),
        "query_template": QUERY_TEMPLATE,
    }


def build_sql(user_input: str) -> str:
    """Build the (vulnerable) SQL string from raw user input via concatenation."""
    return QUERY_TEMPLATE.format(input=user_input)


def execute_raw(user_input: str) -> dict[str, Any]:
    """Run the concatenated query against a fresh throwaway DB.

    Args:
        user_input: Raw user-supplied value (a benign username or a payload).

    Returns:
        Dict with the constructed SQL, returned rows, row count, and a ``leaked``
        flag (True when more than one row came back — i.e. the lookup returned
        rows it should not have).
    """
    sql = build_sql(user_input)
    with _lock:
        conn = _fresh_connection()
        try:
            cursor = conn.execute(sql)  # noqa: S608 - deliberately vulnerable demo
            rows = [dict(row) for row in cursor.fetchall()]
            error: str | None = None
        except sqlite3.Error as exc:
            rows = []
            error = str(exc)
            logger.info("Demo DB rejected payload %r: %s", user_input, error)
        finally:
            conn.close()
    return {
        "constructed_sql": sql,
        "rows": rows,
        "row_count": len(rows),
        # A normal username lookup returns exactly 1 row; more than that means
        # the WHERE clause was subverted and data leaked.
        "leaked": len(rows) > 1,
        "error": error,
    }
