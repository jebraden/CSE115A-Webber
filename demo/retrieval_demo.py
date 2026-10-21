"""Run a local retrieval demo: python -m demo.retrieval_demo."""
import argparse
import json
from pathlib import Path
import sqlite3

from backend.src.app import create_app


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "demo/retrieval_archive"
DATABASE = ROOT / "instance/retrieval-demo.db"


def prepare_demo():
    """Create only the isolated demo database; preserve other archive data."""
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DATABASE) as db:
        db.executescript((ROOT / "backend/db/001_init.sql").read_text())
        for file_id, status in [("manual-html", 200), ("archived-404", 404)]:
            db.execute(
                "INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (file_id, None, "sample.html", "https", 443, "example.com",
                 "/", 0, "GET", "{}", "{}", 0, status,
                 json.dumps({"Content-Type": ["text/html; charset=utf-8"]})),
            )
    return {"DATABASE": DATABASE, "ARCHIVE_ROOT": ARCHIVE}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true",
                        help="Prepare the demo database without starting the server")
    args = parser.parse_args()
    config = prepare_demo()
    if args.prepare_only:
        print(f"Demo database ready: {DATABASE}")
        return
    print("Sample HTML: http://127.0.0.1:3000/files/manual-html/data")
    print("Archived 404: http://127.0.0.1:3000/files/archived-404/data")
    create_app(config).run(host="127.0.0.1", port=3000, debug=False)


if __name__ == "__main__":
    main()
