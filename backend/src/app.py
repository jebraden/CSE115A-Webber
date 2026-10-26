from flask import Flask, jsonify
from typing import Optional, Any
import logging
import platform
import signal
from argparse import ArgumentParser
import sys
import os

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
    app.logger.setLevel(log_level)

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

    parser.add_argument(
        "--production",
        help="use the production web server waitress",
        action="store_true",
    )
    parser.add_argument(
        "--host",
        help="set the address to bind to",
        default="127.0.0.1",
    )
    parser.add_argument(
        "--port",
        help="set the server port",
        type=int,
        default=3000,
    )
    parser.add_argument(
        "--unix-socket",
        help="set the POSIX socket path to listen on",
        default=None,
    )

    parser.add_argument(
        "--debug",
        help="enable Flask debug mode",
        action="store_true",
        default=False,
    )

    result = parser.parse_args()

    if os.name != "posix" and result.unix_socket is not None:
        logger.critical("Cannot bind to a POSIX socket on this platform")
        sys.exit(1)
    elif result.debug and result.production:
        logger.critical("Cannot specify both --production and --debug")
        sys.exit(1)

    return {
        "production": result.production,
        "debug": result.debug,
        "listen": {
            "host": result.host,
            "port": result.port,
            "unix_socket": result.unix_socket,
        },
        "app": {
            "die_with_parent": result.die_with_parent,
            "ppid": result.ppid,
            "log_level": getattr(logging, result.log_level.upper()),
        },
    }


def _start_waitress(
    app: Flask,
    host: str | None,
    port: int,
    unix_socket: str | None,
):
    from waitress import serve  # type: ignore[import-untyped]

    if unix_socket is not None:
        serve(app, unix_socket=unix_socket)
    else:
        serve(app, host=host, port=port)


def _start_flask(
    app: Flask,
    debug: bool,
    host: str | None,
    port: int,
    unix_socket: str | None,
):
    if unix_socket is not None:
        app.run(host=f"unix://{host}", debug=debug)
    else:
        app.run(host=host, port=port, debug=debug)


def main():
    """Main entrypoint."""
    opts = _handle_options()
    app = create_app(**opts["app"])
    if opts["production"]:
        _start_waitress(app, **opts["listen"])
    else:
        _start_flask(app, opts["debug"], **opts["listen"])
