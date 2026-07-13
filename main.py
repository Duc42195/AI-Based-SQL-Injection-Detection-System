"""Entry point / health check for the SQLi Detection System scaffold.

Loads config and logs a startup banner so we can verify the environment and
config wiring end-to-end before the ML modules land.
"""

from __future__ import annotations

from src.utils import get_logger, load_config


def main() -> None:
    """Load config and log a startup banner."""
    cfg = load_config()
    logger = get_logger("main")
    logger.info(
        "Scaffold OK — project=%s | branch1=%s | branch2=%s | api=%s:%s",
        cfg.get_path("project.name"),
        cfg.get_path("branch1_supervised.architecture"),
        cfg.get_path("branch2_anomaly.algorithm"),
        cfg.get_path("api.host"),
        cfg.get_path("api.port"),
    )


if __name__ == "__main__":
    main()
