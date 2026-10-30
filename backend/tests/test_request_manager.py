from src.request_manager import RequestManager
from src.scraping.scraper import PageScraper
import src.request_manager

from src.app import create_app
from unittest.mock import MagicMock, patch
from flask import Flask, request

import pytest
import sqlite3
import json
import time
import os



@pytest.fixture
def test_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_archive.db"
    monkeypatch.setattr(src.request_manager, "db_path", str(db_file))
    monkeypatch.setattr(src.app, "db_path", str(db_file))

    schema = os.path.join(os.path.dirname(__file__), "./../db/001_init.sql")
    with sqlite3.connect(db_file) as db:
        with open(schema, "r") as sql_script:
            db.executescript(sql_script.read())
    return str(db_file)

@pytest.fixture
def test_conn(test_db):
    return sqlite3.connect(test_db)

@pytest.fixture
def insert_snapshot(test_db):
    def insert(snapshot_id="snap-1", url="https://example.com", start_time=100.5, end_time=105.25):
        with sqlite3.connect(test_db) as db:
            db.execute(
                """
                INSERT INTO snapshots (id, url, start_time, end_time)
                VALUES (?, ?, ?, ?)
                """,
                (snapshot_id, url, start_time, end_time),
            )
    return insert

@pytest.fixture
def insert_file(test_db, insert_snapshot):
    def insert(file_id="file-1", snapshot_id="snap-1", **overrides):
        #insert_snapshot(snapshot_id=snapshot_id)

        values = {
            "id": file_id,
            "snapshot_id": snapshot_id,
            "on_disk_path": "/tmp/file-1.html",
            "protocol": "https",
            "port": 443,
            "host": "example.com",
            "remote_path": "/index.html",
            "request_sent_time": 100.0,
            "request_method": "GET",
            "request_headers": json.dumps({}),
            "request_parameters": json.dumps({}),
            "response_recieved_time": 101.0,
            "response_code": 200,
            "response_headers": json.dumps({
                "Content-Type": ["text/html"]
            }),
        }
        values.update(overrides)
        cols = ", ".join(values.keys())
        jsonbs = ["request_parameters", "request_headers", "response_headers"]
        placeholders = ", ".join("jsonb(?)" if col in jsonbs else "?" for col in values)

        with sqlite3.connect(test_db) as db:
            db.execute(
                f"INSERT INTO files ({cols}) VALUES ({placeholders})",
                tuple(values.values()),
            )

    return insert



class TestTimeConversion:

    def _time_dict(self, sec, nsec):
        return {"sec": sec, "nsec": nsec}

    def test_whole_seconds(self, test_conn):
        manager = RequestManager(test_conn)
        assert manager._time(self._time_dict(10, 0)) == 10

    def test_fractional_secons(self, test_conn):
        manager = RequestManager(test_conn)
        assert manager._time(self._time_dict(10, 500_000_000)) == 10.5

    def test_time_spec_whole_seconds(self, test_conn):
        manager = RequestManager(test_conn)
        assert manager._time_spec(10.0) == {
            "sec": 10,
            "nsec": 0,
        }

    def test_time_spec_fract_seconds(self, test_conn):
        manager = RequestManager(test_conn)
        assert manager._time_spec(10.5) == {
            "sec": 10,
            "nsec": 500_000_000
        }

    def test_conversion_safety(self, test_conn):
        manager = RequestManager(test_conn)
        timestamp = 1720000000.123456
        res = manager._time(manager._time_spec(timestamp))

        assert abs(res - timestamp) < 1e-9


class TestRegexp:
    def test_matches(self, test_conn):
        assert RequestManager(test_conn).regexp( r"example\.com", "https://example.com/index.html")

    def test_no_match(self, test_conn):
        assert not RequestManager(test_conn).regexp(r".*", None)

    def test_bad_pattern_throws(self, test_conn):
        with pytest.raises(Exception):
            RequestManager(test_conn).regexp("[", "example.com")

class TestBuildPattern:
    def test_add_regex_cond(self, test_conn):
        manager = RequestManager(test_conn)
        conds = []
        vals = []
        form = {"host": r"example\.com$"}
        manager._build_pattern(form, "host", "host", conds, vals)
        
        assert conds == ["host REGEXP ?"]
        assert vals == [r"example\.com$"]

    def test_omit_empty_pattern(self, test_conn): 
        manager = RequestManager(test_conn)
        conds = []
        vals = []
        manager._build_pattern({}, "host", "host", conds, vals)
        assert conds == []
        assert vals == []

    def test_bad_regex_raises(self, test_conn):
        manager = RequestManager(test_conn)
        with pytest.raises(Exception):
            manager._build_pattern(
                {"host": "["},
                "host",
                "host",
                [],
                []
            )


class TestUrlSubquery:
    def test_add_url_subquery(self, test_conn):
        manager = RequestManager(test_conn)
        conds = []
        vals = []
        form = {"url": r"https://example\.com/.*"}
        manager._url_subquery(form, "url", conds, vals)

        assert conds == [
            "snapshot_id IN (SELECT id FROM snapshots WHERE url REGEXP ?)"
        ] 
        assert vals == [r"https://example\.com/.*"]

    def test_omit_empty_url(self, test_conn):
        manager = RequestManager(test_conn)
        conds = []
        vals = []
        manager._url_subquery({}, "url", conds, vals)
        assert conds == []
        assert vals == []

class TestFileFromRow:
    def make_row(self, path, headers=None, status=200):
        return {
            "id": "some-id-246",
            "on_disk_path": str(path),
            "response_headers": json.dumps(
                headers if headers is not None else {}
            ),
            "response_code": status
        }

    def test_reads_file(self, tmp_path, test_conn):
        manager = RequestManager(test_conn)
        path = tmp_path / "test.html"
        path.write_bytes(b"<html>Hello</html>")

        row = self.make_row(path, {"content-type": ["text/html; charset=utf-8"]},)

        resp, status = manager._file_from_row(row)
        assert status == 200
        assert resp["body"] == b"<html>Hello</html>"
        assert resp["status"] == 200
        assert resp["content_type"] == "text/html; charset=utf-8"

    def test_content_header_case_insensitive(self, tmp_path, test_conn):
        manager = RequestManager(test_conn)
        path = tmp_path / "file.txt"
        path.write_bytes(b"Hi")
        resp, status = manager._file_from_row(
            self.make_row(path, {"Content-Type": ["text/plain"]}),
        )

        assert status == 200
        assert resp["content_type"] == "text/plain"

    def test_missing_file_500s(self, tmp_path, test_conn):
        manager = RequestManager(test_conn)
        path = tmp_path / "fake-file.html"
        resp,status = manager._file_from_row(
            self.make_row(path)
        )
        assert status == 500
        assert "message" in resp

class TestGetSnapshot:
    def test_snapshot_with_files(self, test_db, insert_snapshot, insert_file, test_conn):
        manager = RequestManager(test_conn)
        insert_snapshot(
            snapshot_id="snap-1",
            url="https://example.com",
            start_time=100.5,
            end_time=105.25,
        )
        insert_file(file_id="file-1", snapshot_id="snap-1")
        insert_file(file_id="file-2", snapshot_id="snap-1", remote_path="/example.html",)
        insert_file(file_id="file-3", snapshot_id="snap-2", remote_path="/example2.html",)
        resp, status = manager.get_snapshot("snap-1")

        assert status == 200
        assert resp["id"] == "snap-1"
        assert resp["url"] == "https://example.com"
        assert resp["start_time"] == {
            "sec": 100,
            "nsec": 500_000_000,
        }
        assert resp["end_time"] == {
            "sec": 105,
            "nsec": 250_000_000,
        }
        assert set(resp["files"]) == {"file-1", "file-2"}

    def test_snapshot_no_files(self, test_db, insert_snapshot, test_conn):
        manager = RequestManager(test_conn)
        insert_snapshot(snapshot_id="snap-1")
        resp, status = manager.get_snapshot("snap-1")
        assert status == 200
        assert resp["files"] == []

    def test_snapshot_no_exist(self, test_db):
        manager = RequestManager()
        resp, status = manager.get_snapshot("fake-1")
        assert status == 404

class TestGetFile:
    def test_existing_file_returns_body(self, test_db, tmp_path, insert_snapshot, insert_file, test_conn):
        manager = RequestManager(test_conn)
        insert_snapshot(snapshot_id="snap-1")
        file_path = tmp_path / "file-1.html"
        body=b"Hello, world!"
        file_path.write_bytes(body)
        insert_file(
            file_id="file-1",
            snapshot_id="snap-1",
            response_code=201,
            response_headers=json.dumps({"content-type": ["text/plain"]}),
            on_disk_path=str(file_path)
        )

        resp, status = manager.get_file("file-1")
        assert status == 200
        assert resp["body"] == b"Hello, world!"
        assert resp["status"] == 201
        assert resp["content_type"] == "text/plain"
        
    def test_file_not_found(self, test_db):
        manager = RequestManager()
        resp, status = manager.get_file("fake-1")
        assert status == 404

    def test_binary_return_exact_bytes(self, test_db, insert_snapshot, insert_file, tmp_path, test_conn):
        manager = RequestManager(test_conn)
        insert_snapshot()
        body = b"\x00\xff\x90\x01"
        file_path = tmp_path / "binary.bin"
        file_path.write_bytes(body)
        insert_file(file_id="file-1", snapshot_id="snap-1", on_disk_path=str(file_path))
        resp, status = manager.get_file("file-1")

        assert status == 200
        assert resp["body"] == body


class TestGetFileByUrl:
    def test_repeated_query_params(self, insert_snapshot, insert_file, tmp_path, test_conn):
        insert_snapshot(snapshot_id="snap-1")
        file_path = tmp_path / "test.html"
        file_path.write_bytes(b"test content")

        insert_file(
            file_id="file-1",
            snapshot_id="snap-1",
            on_disk_path=str(file_path),
            remote_path="/index.html",
            request_parameters=json.dumps({"tag": ["a", "b"]}),
        )
        url = (
            "https%3A%2F%2Fexample.com%2Findex.html"
            "%3Ftag%3Da%26tag%3Db"
        )
        app = Flask(__name__)
        manager = RequestManager(test_conn)
        with app.test_request_context("/?tag=a&tag=b"):
            res, status = manager.get_file_by_url("snap-1", url, request)
        assert status == 200
        assert res["body"] == b"test content"

    def test_no_query_params(self, insert_snapshot, insert_file, tmp_path, test_conn):
        insert_snapshot(snapshot_id="snap-1")
        file_path = tmp_path / "test.html"
        file_path.write_bytes(b"test content")

        file_path2 = tmp_path / "red_herring.html"
        file_path2.write_bytes(b"bad news bears")

        insert_file("file-1",
                snapshot_id="snap-1",
                on_disk_path=str(file_path),
                remote_path="/index.html",
                request_parameters=json.dumps({}),
        )
        insert_file("file-2",
                snapshot_id="snap-1",
                on_disk_path=str(file_path2),
                remote_path="/index.html",
                request_parameters=json.dumps({"tag": ["a", "b"]}),
        )

        url = "https%3A%2F%2Fexample.com%2Findex.html"
        app = Flask(__name__)
        manager = RequestManager(test_conn)
        with app.test_request_context(""):
            res, status = manager.get_file_by_url("snap-1", url, request)
        assert status == 200
        assert res["body"] == b"test content"

    def test_no_file(self, insert_snapshot, insert_file, tmp_path, test_conn):
        insert_snapshot(snapshot_id="snap-1")

        insert_file("file-1",
            snapshot_id="snap-1",
            on_disk_path=str(tmp_path / "test.html"),
            remote_path="/index.html",
        )
        url = "https%3A%2F%2Fexample.com%2Findex.html"
        app = Flask(__name__)
        manager = RequestManager(test_conn)
        with app.test_request_context(""):
            res, status = manager.get_file_by_url("snap-1", url, request)
        assert status == 500

    def test_no_file_entry(self, insert_snapshot, insert_file, tmp_path, test_conn):
        url = "https%3A%2F%2Fexample.com%2Findex.html"
        manager = RequestManager(test_conn)
        app = Flask(__name__)
        with app.test_request_context(""):
            res, status = manager.get_file_by_url("snap-1", url, request)
        assert status == 404

class MockRequest:
    form = dict()

class TestQuerySnapshots:
    def test_query_multiple(self, insert_snapshot, test_conn):
        insert_snapshot(snapshot_id="snap-1", start_time=100, end_time=102)
        insert_snapshot(snapshot_id="snap-2", start_time=103, end_time=104)
        insert_snapshot(snapshot_id="snap-3", start_time=104, end_time=104)
        insert_snapshot(snapshot_id="snap-4", start_time=105, end_time=106)

        manager = RequestManager(test_conn)
        request = MockRequest()
        request.form = {
            "start_time": manager._time_spec(104),
            "end_time": manager._time_spec(106)
        }
        res, status = manager.query_snapshots(request)
        assert status == 200

        content = res["content"]
        assert content == ["snap-3", "snap-4"]

    def test_query_regex(self, insert_snapshot, test_conn):
        insert_snapshot(snapshot_id="snap-1", url="http://example.com")
        insert_snapshot(snapshot_id="snap-2", url="https://example.com")

        manager = RequestManager(test_conn)
        request = MockRequest()
        request.form = {
            "url": "^http:\\/\\/example"
        }
        res, status = manager.query_snapshots(request)
        assert status == 200
        content = res["content"]
        assert content == ["snap-1",]

    def test_query_empty_form(self, insert_snapshot, test_conn):
        insert_snapshot(snapshot_id="snap-1", start_time=100, end_time=102)
        insert_snapshot(snapshot_id="snap-2", start_time=103, end_time=104)
        insert_snapshot(snapshot_id="snap-3", start_time=104, end_time=104)
        insert_snapshot(snapshot_id="snap-4", start_time=105, end_time=106)
        manager = RequestManager()
        request = MockRequest()
        request.form = {}
        res, status = manager.query_snapshots(request)
        assert status == 200
        content = res["content"]
        assert content == ["snap-1", "snap-2", "snap-3", "snap-4"]


class TestQueryFiles:
    def test_query_no_filters(self, insert_snapshot, insert_file, test_conn):
        insert_snapshot(snapshot_id="snap-1", url="https://example.com")
        insert_snapshot(snapshot_id="snap-2", url="https://example.com", start_time=200, end_time=201)

        insert_file(file_id="file-1", snapshot_id="snap-1")
        insert_file(file_id="file-2", snapshot_id="snap-1")
        insert_file(file_id="file-3", snapshot_id="snap-2")

        request = MockRequest()
        request.form = {}

        manager = RequestManager(test_conn)

        res, status = manager.query_files(request)
        assert status == 200

        content = res["content"]
        assert content == [
            {
                "snapshot_id": "snap-1",
                "file_id": "file-1",
            },
            {
                "snapshot_id": "snap-1",
                "file_id": "file-2",
            },
            {
                "snapshot_id": "snap-2",
                "file_id": "file-3",
            }
        ]

    def test_query_snapshot_url_regex(self, insert_snapshot, insert_file, test_conn):
        insert_snapshot(
            snapshot_id="snap-1",
            url="https://example.com/index.html",
        )
        insert_snapshot(
            snapshot_id="snap-2",
            url="https://example.com/about",
        )
        insert_file(file_id="file-1", snapshot_id="snap-1")
        insert_file(file_id="file-2", snapshot_id="snap-2")

        manager = RequestManager(test_conn)
        request = MockRequest()
        request.form = {"url": "/index\\.html$"}

        res, status = manager.query_files(request)
    
        print(res["content"])
        assert status == 200
        assert res["content"] ==[
            {"snapshot_id": "snap-1", "file_id": "file-1"}
        ]
        

    def test_query_combined_filters(self, insert_snapshot, insert_file, test_conn):
        insert_snapshot(
            snapshot_id="snap-1",
            url="https://example.com/index.html",
            start_time=100,
            end_time=110,
        )
        insert_snapshot(
            snapshot_id="snap-2",
            url="https://other.com/index.html",
            start_time=100,
            end_time=110,
        )

        insert_file(
            file_id="file-1",
            snapshot_id="snap-1",
            host="example.com",
            protocol="https",
            port=445,
            remote_path="/index.html",
            response_code=200,
            request_sent_time=104,
            response_recieved_time=105,
        )

        insert_file(
            file_id="file-2",
            snapshot_id="snap-1",
            host="other.com",
            protocol="https",
            port=443,
            remote_path="/index.html",
            response_code=200,
            request_sent_time=105,
        )

        insert_file(
            file_id="file-3",
            snapshot_id="snap-1",
            host="example.com",
            protocol="https",
            port=443,
            remote_path="/index.html",
            response_code=200,
            request_sent_time=105,
        )
        insert_file(
            file_id="file-4",
            snapshot_id="snap-1",
            host="example.com",
            protocol="https",
            port=8443,
            remote_path="/index.html",
            response_code=200,
            request_sent_time=105,
        )
        insert_file(
            file_id="file-5",
            snapshot_id="snap-1",
            host="example.com",
            protocol="https",
            port=443,
            remote_path="/about.html",
            response_code=200,
            request_sent_time=105,
        )
        insert_file(
            file_id="file-6",
            snapshot_id="snap-1",
            host="example.com",
            protocol="https",
            port=443,
            remote_path="/index.html",
            response_code=404,
            request_sent_time=105,
        )

        insert_file(
            file_id="file-7",
            snapshot_id="snap-2",
            host="example.com",
            protocol="https",
            port=443,
            remote_path="/index.html",
            response_code=200,
            request_sent_time=105,
        )

        manager = RequestManager(test_conn)
        request = MockRequest()
        request.form = {
            "start_time": manager._time_spec(104),
            "end_time": manager._time_spec(106),
            "host": r"^example\.com$",
            "protocol": "https",
            "path": r"^/index\.html$",
            "url": r"^https://example\.com/",
            "port": 445,
            "status_codes": [200],
        }
        res, status = manager.query_files(request)
        assert status == 200
        assert res["content"] == [
            {"snapshot_id": "snap-1", "file_id": "file-1"}
        ]

class TestDeleteSnapshot:
    def delete_not_exist(self, test_conn):
        manager = RequestManager(test_conn)
        resp, status = manager.delete_snapshot("snap-1")
        assert status == 404

    def delete_exist_has_files(self, tmp_path, insert_snapshot, insert_file, test_conn):
        manager = RequestManager(test_conn)

        insert_snapshot(snapshot_id="snap-1")

        path = tmp_path / "test.html"
        path.write_bytes(b"hello")

        insert_file(file_id="file-1", snapshot_id="snap-1", on_disk_path=str(path))

        res, status = manager.delete_snapshot("snap-1")
        assert status == 202
        assert not path.exists()

        _, status2 = manager.get_file("file-1")
        assert status2 == 404

        _, status3 = maager.get_snapshot("snap-1")
        assert status3 == 404


class TestProcessInterval:
    def test_process_single_interval(self, test_db, insert_snapshot, insert_file, tmp_path, test_conn):
        manager = RequestManager(test_conn)
        insert_snapshot(
            snapshot_id="snap-1",
            url="https://example.com",
            start_time=120.0,
            end_time=125.0,
        )
        insert_snapshot(
            snapshot_id="snap-2",
            url="https://example.com",
            start_time=150.0,
            end_time=155.0,
        )

        file1 = tmp_path / "file1.html"
        file1.write_bytes(b"aaa")

        file2 = tmp_path / "file2.html"
        file2.write_bytes(b"bbb")

        file3 = tmp_path / "file3.html"
        file3.write_bytes(b"ccc")

        insert_file(
            file_id="file-1",
            snapshot_id="snap-1",
            on_disk_path=str(file1),
            host="cdn.example.com",
        )
        insert_file(
            file_id="file-2",
            snapshot_id="snap-1",
            on_disk_path=str(file2),
            host="cdn.example.com",
        )
        insert_file(
            file_id="file-3",
            snapshot_id="snap-2",
            on_disk_path=str(file3),
            host="example.com",
        )
        db = sqlite3.connect(test_db)
        db.row_factory = sqlite3.Row
        interval = {
            "start": {"sec": 100, "nsec": 0},
            "end": {"sec": 200, "nsec": 0},
        }
        try:
            res, status = manager._process_interval(interval, db)
        finally:
            db.close()
        assert status == 200
        assert res["snapshots"] == 2
        assert res["files"] == 3
        assert res["size"] == 9
        assert res["urls"] == 1
        assert res["hosts"] == 2

    def test_process_bad_interval(self, test_conn):
        manager = RequestManager(test_conn)

        interval = manager._build_interval(200, 100) 
        res, status = manager._process_interval(interval, None)
        assert status == 400

    def test_process_no_results(self, test_db, test_conn):
        manager = RequestManager(test_conn)
        db = sqlite3.connect(test_db)
        db.row_factory = sqlite3.Row
        interval = manager._build_interval(100, 200)
        try:
            res, status = manager._process_interval(interval, db)
        finally:
            db.close()
        assert status == 200
        assert res["snapshots"] == 0
        assert res["files"] == 0
        assert res["size"] == 0
        assert res["urls"] == 0
        assert res["hosts"] == 0


class TestGetLimits:
    def test_no_snaps(self, test_db):
        manager = RequestManager()
        res, status = manager.get_limits()
        assert status == 200
        assert res == {
            "first_snapshot": None,
            "last_snapshot": None
        }

    def test_get_right_snaps(self, test_db, insert_snapshot):
        manager = RequestManager()
        insert_snapshot(snapshot_id="snap-1", start_time=100)
        insert_snapshot(snapshot_id="snap-2", start_time=102)
        insert_snapshot(snapshot_id="snap-3", start_time=104)
        insert_snapshot(snapshot_id="snap-4", start_time=106)

        res, status = manager.get_limits()
        assert status == 200
        assert res == {
            "first_snapshot": manager._time_spec(100),
            "last_snapshot": manager._time_spec(106)
        }

            


        
class TestFlaskRoutes:
    def setup(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_get_snapshot(self, insert_snapshot):
        self.setup()
        insert_snapshot(snapshot_id="snap-1")
        resp = self.client.get("/snapshots/snap-1")

        resp2 = self.client.get("/snapshots/snap-2")

        assert resp.status_code == 200
        assert resp2.status_code == 404








