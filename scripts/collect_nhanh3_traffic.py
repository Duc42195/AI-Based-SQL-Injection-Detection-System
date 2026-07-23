"""Collect Branch 3 session data (Cách B) by running sqlmap through mitmproxy.
"""

from __future__ import annotations

import csv
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from src.utils import get_logger, load_config

logger = get_logger(__name__)

_HERE = Path(__file__).resolve().parent
_PROJECT = _HERE.parent

TARGET_URL = os.getenv("SQLI_TARGET_URL", "http://localhost:42801")
PROXY_HOST = os.getenv("MITMPROXY_HOST", "127.0.0.1")
PROXY_PORT = int(os.getenv("MITMPROXY_PORT", "8080"))


def _check_deps() -> None:
    if not shutil.which("mitmdump"):
        logger.error("mitmdump not found")
        sys.exit(1)
    if not shutil.which("sqlmap"):
        logger.error("sqlmap not found")
        sys.exit(1)


def _start_mitmdump(flow_file: Path) -> subprocess.Popen:
    logger.info("Starting mitmdump -> %s", flow_file)
    return subprocess.Popen(
        [
            "mitmdump",
            "--listen-host", PROXY_HOST,
            "--listen-port", str(PROXY_PORT),
            "--save-stream-file", str(flow_file),
            "--set", "block_global=false",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


INTER_TECH_DELAY = int(os.getenv("SQLI_INTER_TECH_DELAY", "120"))


def _run_sqlmap(label: str, url: str, technique: str, out_root: Path) -> None:
    out_dir = str(out_root / label)
    logger.info("sqlmap [%s]: %s  technique=%s", label, url, technique)
    subprocess.run(
        [
            "sqlmap",
            "-u", url,
            "--batch",
            "--technique", technique,
            "--level", "2",
            "--risk", "2",
            "--time-sec", "2",
            "--proxy", f"http://{PROXY_HOST}:{PROXY_PORT}",
            "--flush-session",
            "--random-agent",
            "--output-dir", out_dir,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=240,
    )
    logger.info("sqlmap [%s] done", label)
    logger.info("Sleeping %ds before next run (idle gap for session split) ...", INTER_TECH_DELAY)
    time.sleep(INTER_TECH_DELAY)


def _collect_benign(output_csv: Path) -> None:
    import csv, time, urllib.request
    logger.info("Collecting benign traffic ...")
    proxy_hdlr = urllib.request.ProxyHandler({
        "http": f"http://{PROXY_HOST}:{PROXY_PORT}",
        "https": f"http://{PROXY_HOST}:{PROXY_PORT}",
    })
    opener = urllib.request.build_opener(proxy_hdlr)
    rows = []
    for i in range(5):
        try:
            opener.open(f"{TARGET_URL}/", timeout=5)
        except Exception:
            pass
        for uid in range(1, 6):
            for ep in ["user", "product", "profile", "order"]:
                q = f"id={uid}" if ep in ("user", "product") else f"uid={uid}" if ep == "profile" else f"oid={uid}"
                try:
                    opener.open(f"{TARGET_URL}/{ep}?{q}", timeout=5)
                except Exception:
                    pass
        try:
            opener.open(f"{TARGET_URL}/search?q=test", timeout=5)
        except Exception:
            pass
        time.sleep(0.02)
    logger.info("Benign traffic done")


def _stop_mitmdump(proc: subprocess.Popen) -> None:
    logger.info("Stopping mitmdump ...")
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _export_flows(flow_file: Path, output_csv: Path) -> None:
    if not flow_file.exists() or flow_file.stat().st_size == 0:
        logger.warning("Flow file %s missing or empty", flow_file)
        return

    logger.info("Exporting flows to %s ...", output_csv)
    try:
        from mitmproxy import http
        from mitmproxy.io import FlowReader
    except ImportError:
        logger.warning("mitmproxy Python package not importable — skipping export")
        return

    rows: list[dict] = []
    try:
        with flow_file.open("rb") as f:
            reader = FlowReader(f)
            for flow in reader.stream():
                if not isinstance(flow, http.HTTPFlow):
                    continue
                req = flow.request
                resp = flow.response
                rows.append({
                    "timestamp": flow.request.timestamp_start,
                    "method": req.method,
                    "url": req.pretty_url,
                    "path": req.path,
                    "query": str(req.query) if req.query else "",
                    "request_body": req.get_text() or "",
                    "status_code": resp.status_code if resp else 0,
                    "response_body": resp.get_text() if resp else "",
                    "content_type": resp.headers.get("content-type", "") if resp else "",
                })
    except Exception as e:
        logger.warning("Failed to read flow file: %s", e)
        return

    if not rows:
        logger.warning("No HTTP flows found in %s", flow_file)
        return

    fieldnames = [
        "timestamp", "method", "url", "path", "query",
        "request_body", "status_code", "response_body", "content_type",
    ]
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    logger.info("Exported %d HTTP flows to %s", len(rows), output_csv)


def main() -> None:
    cfg = load_config()
    _check_deps()

    raw_dir = Path(cfg.get_path("paths.data_raw", "data/raw"))
    sessions_dir = raw_dir / "nhanh3_sqlmap_sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    sqlmap_out_root = sessions_dir / "sqlmap_output"
    sqlmap_out_root.mkdir(parents=True, exist_ok=True)

    flow_file = sessions_dir / "capture.flow"
    if flow_file.exists():
        flow_file.unlink()

    proc = _start_mitmdump(flow_file)
    time.sleep(1)

    try:
        endpoints = [
            ("user_get", "/user?id=1"),
            ("search_get", "/search?q=admin"),
            ("product_get", "/product?id=1"),
            ("profile_get", "/profile?uid=1"),
            ("order_get", "/order?oid=1"),
        ]
        techniques = ["B", "T", "U", "S", "E", "Q"]
        for label, url_suffix in endpoints:
            logger.info("--- %s (sleeping %ds before starting for idle gap) ---", label, INTER_TECH_DELAY)
            time.sleep(INTER_TECH_DELAY)
            for tech in techniques:
                _run_sqlmap(f"{label}_{tech}", f"{TARGET_URL}{url_suffix}", tech, sqlmap_out_root)
        try:
            output_csv = sessions_dir / "nhanh3_raw_traffic.csv"
            _collect_benign(output_csv)
        except Exception as e:
            logger.warning("Benign collection failed (non-fatal): %s", e)
    finally:
        _stop_mitmdump(proc)
        _export_flows(flow_file, output_csv)

    logger.info("=== Done ===")


if __name__ == "__main__":
    main()
