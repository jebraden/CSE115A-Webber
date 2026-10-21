from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3

from flask import Flask, Response, jsonify


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=os.environ.get("WEBBER_DATABASE", "instance/webber.db"),
        ARCHIVE_ROOT=os.environ.get("WEBBER_ARCHIVE_ROOT", "instance/archive"),
    )
    if config:
        app.config.update(config)

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    @app.get("/files/<file_id>/data")
    def file_data(file_id):
        try:
            # Read-only mode prevents an incorrect configuration from creating
            # an empty database and concealing the underlying storage problem.
            database = Path(app.config["DATABASE"]).resolve()
            with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
                db.row_factory = sqlite3.Row
                row = db.execute(
                    "SELECT on_disk_path, response_code, response_headers "
                    "FROM files WHERE id = ?", (file_id,)
                ).fetchone()
            if row is None:
                return jsonify({}), 404

            root = Path(app.config["ARCHIVE_ROOT"]).resolve()
            path = (root / row["on_disk_path"]).resolve()
            if not path.is_relative_to(root):
                raise ValueError("Stored path is outside the archive directory")

            # The schema uses a BLOB column; writers must store UTF-8 JSON
            # bytes (or JSON text), not SQLite's internal JSONB representation.
            headers = json.loads(row["response_headers"])
            content_type = "application/octet-stream"
            for name, values in headers.items():
                if name.lower() == "content-type":
                    if not isinstance(values, list) or not values or not isinstance(values[0], str):
                        raise ValueError("Invalid stored Content-Type")
                    content_type = values[0]
                    break
            status = row["response_code"]
            if not isinstance(status, int) or not 200 <= status <= 599:
                raise ValueError("Invalid archived response status")
            return Response(path.read_bytes(), status=status, content_type=content_type)
        except (OSError, sqlite3.Error, ValueError, TypeError, AttributeError):
            app.logger.exception("Unable to retrieve archived file %s", file_id)
            return jsonify({"message": "Unable to read the archived file."}), 500

    return app


def main():
    """Main entrypoint."""
    app = create_app()
    app.run(host="127.0.0.1", port=3000, debug=False)
