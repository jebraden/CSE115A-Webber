import json
from pathlib import Path
import sqlite3

import pytest

from backend.src.app import create_app


@pytest.fixture
def archive(tmp_path):
    root = tmp_path / "archive"
    root.mkdir()
    database = tmp_path / "archive.db"
    schema = Path(__file__).parents[1] / "db/001_init.sql"
    with sqlite3.connect(database) as db:
        db.executescript(schema.read_text())
    app = create_app({"TESTING": True, "DATABASE": database, "ARCHIVE_ROOT": root})
    return app.test_client(), database, root


def store(database, root, *, status=200, path="page.html", headers=None):
    content = b'<!doctype html><p>Saved source: \xc3\xa9</p>\r\n'
    (root / "page.html").write_bytes(content)
    with sqlite3.connect(database) as db:
        db.execute(
            "INSERT INTO files VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("file-1", None, path, "https", 443, "example.com", "/", 0,
             "GET", b"{}", b"{}", 0, status,
             json.dumps(headers or {"content-type": ["text/html; charset=utf-8"]}).encode()),
        )
    return content


@pytest.mark.parametrize("status", [200, 404, 500])
def test_original_bytes_type_and_status(archive, status):
    client, database, root = archive
    content = store(database, root, status=status)
    response = client.get("/files/file-1/data")
    assert response.status_code == status
    assert response.data == content
    assert response.headers["Content-Type"] == "text/html; charset=utf-8"


def test_unknown_id(archive):
    client, _, _ = archive
    response = client.get("/files/not-found/data")
    assert response.status_code == 404
    assert response.json == {}


@pytest.mark.parametrize("path", ["missing.html", "../outside.html"])
def test_missing_or_escaped_path(archive, path):
    client, database, root = archive
    store(database, root, path=path)
    (root.parent / "outside.html").write_text("private")
    response = client.get("/files/file-1/data")
    assert response.status_code == 500
    assert response.json == {"message": "Unable to read the archived file."}
    assert b"private" not in response.data


def test_missing_database_does_not_create_it(tmp_path):
    database = tmp_path / "missing.db"
    client = create_app({"TESTING": True, "DATABASE": database}).test_client()
    assert client.get("/files/file-1/data").status_code == 500
    assert not database.exists()


def test_id_is_not_sql(archive):
    client, database, root = archive
    store(database, root)
    assert client.get("/files/'%20OR%201=1--/data").status_code == 404


def test_symlink_cannot_escape_archive(archive):
    client, database, root = archive
    store(database, root, path="link.html")
    outside = root.parent / "outside.html"
    outside.write_text("private")
    (root / "link.html").symlink_to(outside)
    assert client.get("/files/file-1/data").status_code == 500


def test_invalid_metadata_is_storage_error(archive):
    client, database, root = archive
    store(database, root)
    with sqlite3.connect(database) as db:
        db.execute("UPDATE files SET response_headers = ?", (b"not json",))
    assert client.get("/files/file-1/data").status_code == 500


def test_binary_content_and_default_type(archive):
    client, database, root = archive
    store(database, root, headers={"Other": ["value"]})
    (root / "page.html").write_bytes(b"\x00\xff\x80")
    response = client.get("/files/file-1/data")
    assert response.data == b"\x00\xff\x80"
    assert response.content_type == "application/octet-stream"
