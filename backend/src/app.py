from flask import Flask, jsonify
from typing import Optional, Any
import logging
import platform
import signal
from argparse import ArgumentParser

logger = logging.getLogger(__name__)


def _setup_die_with_parent(ppid: int | None):
    if ppid is None:
        logger.warning(
            "Using `die_with_parent=True` without `ppid` is subject to "
            "race conditions."
        )

    system = platform.system()
    if system == "Linux":
        from .platforms import linux

        linux.die_with_parent(signal.SIGTERM, ppid)
    else:
        from .platforms import parent_watch

        parent_watch.die_with_parent(signal.SIGTERM, ppid)


def create_app(
    die_with_parent: Optional[bool] = False,
    ppid: Optional[int] = None,
    log_level: int = logging.WARN,
) -> Flask:
    """Create an return a WSGI object to start the server with.

    Arguments:
    die_with_parent -- arrange for the server to be killed when its parent
                       process exits
    ppid -- The PID of the process that started this process. This is
            necessary to avoid a race condition when using `die_with_parent`.
    log_level -- detail level for the logger (one of the logging.* constants)

    Returns: the WSGI object
    """
    logging.basicConfig(level=log_level)

    if die_with_parent:
        _setup_die_with_parent(ppid)

    app = Flask(__name__)

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    return app


def _handle_options() -> dict[str, Any]:
    """Parse command line arguments."""
    parser = ArgumentParser(
        description="Run the Webber backend with a development flask server."
    )
    parser.add_argument(
        "--die-with-parent",
        help="terminate this process when its parent exits",
        action="store_true",
    )
    parser.add_argument(
        "--ppid",
        help="the PID of the process that started this one",
        type=int,
    )
    parser.add_argument(
        "--log-level",
        help="set the logger detail level",
        choices=["debug", "info", "warning", "error", "critical"],
        type=str.lower,
        default="warning",
    )

    result = parser.parse_args()
    return {
        "die_with_parent": result.die_with_parent,
        "ppid": result.ppid,
        "log_level": getattr(logging, result.log_level.upper()),
    }


def main():
    """Main entrypoint."""
    app = create_app(**_handle_options())
    app.run(host="127.0.0.1", port=3000, debug=False)
