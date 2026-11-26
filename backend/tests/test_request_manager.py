from src.request_manager import RequestManager, _sql_regexp
from src.scraping.scraper import PageScraper, HyperlinkRules
import src.request_manager

from src.app import create_app
from unittest.mock import AsyncMock, MagicMock, patch
from flask import Flask, request

import pytest
import sqlite3
import json
import time
import os
import threading
import concurrent.futures


@pytest.fixture
def test_db(tmp_path):
    db_file = str(tmp_path / "test_archive.db")
    with patch("src.request_manager.DB_PATH", db_file), patch(
        "src.app.DB_PATH", db_file
    ):
        schema = os.path.join(
            os.path.dirname(__file__), "./../db/001_init.sql"
        )
        with sqlite3.connect(db_file) as db:
            with open(schema, "r") as sql_script:
                db.executescript(sql_script.read())
        yield db_file


@pytest.fixture
def insert_snapshot(test_db):
    def insert(
        snapshot_id="snap-1",
        url="https://example.com",
        start_time=100.5,
        end_time=105.25,
    ):
        with sqlite3.connect(test_db) as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;
                """)
            db.execute(
                """
                INSERT INTO snapshots (id, url, start_time, end_time)
                VALUES (?, ?, ?, ?)
                """,
                (snapshot_id, url, start_time, end_time),
            )

    return insert


@pytest.fixture
def manager(test_db):
    with RequestManager(test_db) as manager:
        yield manager


@pytest.fixture
def insert_file(test_db, insert_snapshot):
    def insert(file_id="file-1", snapshot_id="snap-1", **overrides):
        # insert_snapshot(snapshot_id=snapshot_id)

        values = {
            "id": file_id,
            "snapshot_id": snapshot_id,
            "on_disk_path": "/tmp/file-1.html",
            "file_size": 100,
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
            "response_headers": json.dumps({"Content-Type": ["text/html"]}),
        }
        values.update(overrides)
        cols = ", ".join(values.keys())
        jsonbs = ["request_parameters", "request_headers", "response_headers"]
        placeholders = ", ".join(
            "jsonb(?)" if col in jsonbs else "?" for col in values
        )

        with sqlite3.connect(test_db) as db:
            db.execute(
                f"INSERT INTO files ({cols}) VALUES ({placeholders})",
                tuple(values.values()),
            )

    return insert


class TestTimeConversion:

    def _time_dict(self, sec, nsec):
        return {"sec": sec, "nsec": nsec}

    def test_whole_seconds(self, manager):
        assert manager._time(self._time_dict(10, 0)) == 10

    def test_fractional_secons(self, manager):
        assert manager._time(self._time_dict(10, 500_000_000)) == 10.5

    def test_time_spec_whole_seconds(self, manager):
        assert manager._time_spec(10.0) == {
            "sec": 10,
            "nsec": 0,
        }

    def test_time_spec_fract_seconds(self, manager):
        assert manager._time_spec(10.5) == {"sec": 10, "nsec": 500_000_000}

    def test_conversion_safety(self, manager):
        timestamp = 1720000000.123456
        res = manager._time(manager._time_spec(timestamp))

        assert res == pytest.approx(timestamp)


class TestRegexp:
    def test_matches(self):
        assert _sql_regexp(r"example\.com", "https://example.com/index.html")

    def test_no_match(self):
        assert not _sql_regexp(r".*", None)

    def test_bad_pattern_throws(self):
        with pytest.raises(Exception):
            _sql_regexp("[", "example.com")


class TestBuildPattern:
    def test_add_regex_cond(self, manager):
        conds: list[str] = []
        vals: list[str] = []
        form = {"host": r"example\.com$"}
        manager._build_pattern(form, "host", "host", conds, vals)

        assert conds == ["host REGEXP ?"]
        assert vals == [r"example\.com$"]

    def test_omit_empty_pattern(self, manager):
        conds: list[str] = []
        vals: list[str] = []
        manager._build_pattern({}, "host", "host", conds, vals)
        assert conds == []
        assert vals == []

    def test_bad_regex_raises(self, manager):
        with pytest.raises(Exception):
            manager._build_pattern({"host": "["}, "host", "host", [], [])


class TestUrlSubquery:
    def test_add_url_subquery(self, manager):
        conds: list[str] = []
        vals: list[str] = []
        form = {"url": r"https://example\.com/.*"}
        manager._url_subquery(form, "url", conds, vals)

        assert conds == [
            "snapshot_id IN (SELECT id FROM snapshots WHERE url REGEXP ?)"
        ]
        assert vals == [r"https://example\.com/.*"]

    def test_omit_empty_url(self, manager):
        conds: list[str] = []
        vals: list[str] = []
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
            "response_code": status,
        }

    def test_reads_file(self, tmp_path, manager):
        path = tmp_path / "test.html"
        path.write_bytes(b"<html>Hello</html>")

        row = self.make_row(
            path,
            {"content-type": ["text/html; charset=utf-8"]},
        )

        resp, status = manager._file_from_row(row)
        assert status == 200
        assert resp["body"] == b"<html>Hello</html>"
        assert resp["status"] == 200
        assert resp["content_type"] == "text/html; charset=utf-8"

    def test_content_header_case_insensitive(self, tmp_path, manager):
        path = tmp_path / "file.txt"
        path.write_bytes(b"Hi")
        resp, status = manager._file_from_row(
            self.make_row(path, {"Content-Type": ["text/plain"]}),
        )

        assert status == 200
        assert resp["content_type"] == "text/plain"

    def test_missing_file_500s(self, tmp_path, manager):
        path = tmp_path / "fake-file.html"
        resp, status = manager._file_from_row(self.make_row(path))
        assert status == 500
        assert "message" in resp


class MockScraper:
    def __init__(
        self,
        db_conn=None,
        debug=False,
        hyperlink_rules=HyperlinkRules(),
        snapshot_url=None,
        depth=0,
    ):
        self.db = db_conn
        self.archive_page = AsyncMock(return_value="snap-1")
        self.snapshot_url = snapshot_url
        self.depth = depth
        self.hyperlink_rules = hyperlink_rules


class TestCreateSnapshot:
    def test_create_basic(self, monkeypatch, insert_snapshot, manager):
        instances = []
        original_init = MockScraper.__init__

        def capture_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            instances.append(self)

        monkeypatch.setattr(MockScraper, "__init__", capture_init)
        monkeypatch.setattr("src.request_manager.PageScraper", MockScraper)

        request = MockRequest()
        request.json_dat = {
            "url": "https://example.com",
            "request_options": {
                "method": "GET",
                "headers": {"Authorization": ["Basic"]},
            },
        }

        resp, status = manager.create_snapshot(request)

        assert status == 201
        assert resp == {"id": "snap-1"}

        assert len(instances) == 1
        rules = instances[0].hyperlink_rules
        assert rules.max_depth == 0
        assert rules.top_domain_only == True
        assert rules.blacklist_domains == set()
        assert rules.whitelist_domains == set()

    def test_create_with_rules(self, monkeypatch, manager, insert_snapshot):
        instances = []
        original_init = MockScraper.__init__

        def capture_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            instances.append(self)

        monkeypatch.setattr(MockScraper, "__init__", capture_init)
        monkeypatch.setattr("src.request_manager.PageScraper", MockScraper)

        request = MockRequest()
        request.json_dat = {
            "url": "https://example.com",
            "request_options": {
                "method": "GET",
                "headers": {
                    "Authorization": ["Basic"],
                },
            },
            "crawl": {
                "enable": True,
                "top_level_only": False,
                "depth": 9,
                "whitelist_domains": ["some_domain"],
                "blacklist_domains": ["some_other"],
            },
        }

        resp, status = manager.create_snapshot(request)

        assert status == 201
        assert resp == {"id": "snap-1"}

        assert len(instances) == 1
        rules = instances[0].hyperlink_rules
        assert rules.max_depth == 9
        assert rules.top_domain_only == False
        assert rules.blacklist_domains == {"some_other"}
        assert rules.whitelist_domains == {"some_domain"}


class TestGetSnapshot:
    def test_snapshot_with_files(self, manager, insert_snapshot, insert_file):
        insert_snapshot(
            snapshot_id="snap-1",
            url="https://example.com",
            start_time=100.5,
            end_time=105.25,
        )
        insert_file(file_id="file-1", snapshot_id="snap-1")
        insert_file(
            file_id="file-2",
            snapshot_id="snap-1",
            remote_path="/example.html",
        )
        insert_file(
            file_id="file-3",
            snapshot_id="snap-2",
            remote_path="/example2.html",
        )
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

    def test_snapshot_no_files(self, manager, insert_snapshot):
        insert_snapshot(snapshot_id="snap-1")
        resp, status = manager.get_snapshot("snap-1")
        assert status == 200
        assert resp["files"] == []

    def test_snapshot_no_exist(self, manager):
        resp, status = manager.get_snapshot("fake-1")
        assert status == 404


class TestGetFile:
    def test_existing_file_returns_body(
        self, manager, tmp_path, insert_snapshot, insert_file
    ):
        insert_snapshot(snapshot_id="snap-1")
        file_path = tmp_path / "file-1.html"
        body = b"Hello, world!"
        file_path.write_bytes(body)
        insert_file(
            file_id="file-1",
            snapshot_id="snap-1",
            response_code=201,
            response_headers=json.dumps({"content-type": ["text/plain"]}),
            on_disk_path=str(file_path),
        )

        resp, status = manager.get_file("file-1")
        assert status == 200
        assert resp["body"] == b"Hello, world!"
        assert resp["status"] == 201
        assert resp["content_type"] == "text/plain"

    def test_file_not_found(self, manager):
        resp, status = manager.get_file("fake-1")
        assert status == 404

    def test_binary_return_exact_bytes(
        self, manager, insert_snapshot, insert_file, tmp_path
    ):
        insert_snapshot()
        body = b"\x00\xff\x90\x01"
        file_path = tmp_path / "binary.bin"
        file_path.write_bytes(body)
        insert_file(
            file_id="file-1", snapshot_id="snap-1", on_disk_path=str(file_path)
        )
        resp, status = manager.get_file("file-1")

        assert status == 200
        assert resp["body"] == body


class TestGetFileByUrl:
    def test_repeated_query_params(
        self, insert_snapshot, insert_file, tmp_path, manager
    ):
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
        url = "https%3A%2F%2Fexample.com%2Findex.html" "%3Ftag%3Da%26tag%3Db"
        app = Flask(__name__)
        with app.test_request_context("/?tag=a&tag=b"):
            res, status = manager.get_file_by_url("snap-1", url, request)
        assert status == 200
        assert res["body"] == b"test content"

    def test_no_query_params(
        self, insert_snapshot, insert_file, tmp_path, manager
    ):
        insert_snapshot(snapshot_id="snap-1")
        file_path = tmp_path / "test.html"
        file_path.write_bytes(b"test content")

        file_path2 = tmp_path / "red_herring.html"
        file_path2.write_bytes(b"bad news bears")

        insert_file(
            "file-1",
            snapshot_id="snap-1",
            on_disk_path=str(file_path),
            remote_path="/index.html",
            request_parameters=json.dumps({}),
        )
        insert_file(
            "file-2",
            snapshot_id="snap-1",
            on_disk_path=str(file_path2),
            remote_path="/index.html",
            request_parameters=json.dumps({"tag": ["a", "b"]}),
        )

        url = "https%3A%2F%2Fexample.com%2Findex.html"
        app = Flask(__name__)
        with app.test_request_context(""):
            res, status = manager.get_file_by_url("snap-1", url, request)
        assert status == 200
        assert res["body"] == b"test content"

    def test_no_file(self, insert_snapshot, insert_file, tmp_path, manager):
        insert_snapshot(snapshot_id="snap-1")

        insert_file(
            "file-1",
            snapshot_id="snap-1",
            on_disk_path=str(tmp_path / "test.html"),
            remote_path="/index.html",
        )
        url = "https%3A%2F%2Fexample.com%2Findex.html"
        app = Flask(__name__)
        with app.test_request_context(""):
            res, status = manager.get_file_by_url("snap-1", url, request)
        assert status == 500

    def test_no_file_entry(
        self, insert_snapshot, insert_file, tmp_path, manager
    ):
        url = "https%3A%2F%2Fexample.com%2Findex.html"
        app = Flask(__name__)
        with app.test_request_context(""):
            res, status = manager.get_file_by_url("snap-1", url, request)
        assert status == 404


class MockRequest:
    def __init__(self):
        self.json_dat = dict()

    def get_json(self, silent=False):
        return self.json_dat


class TestQuerySnapshots:
    def test_query_multiple(self, insert_snapshot, manager):
        insert_snapshot(snapshot_id="snap-1", start_time=100, end_time=102)
        insert_snapshot(snapshot_id="snap-2", start_time=103, end_time=104)
        insert_snapshot(snapshot_id="snap-3", start_time=104, end_time=104)
        insert_snapshot(snapshot_id="snap-4", start_time=105, end_time=106)

        request = MockRequest()
        request.json_dat = {
            "start_time": manager._time_spec(104),
            "end_time": manager._time_spec(106),
        }
        res, status = manager.query_snapshots(request)
        assert status == 200

        content = res["content"]
        assert content == ["snap-3", "snap-4"]

    def test_query_regex(self, insert_snapshot, manager):
        insert_snapshot(snapshot_id="snap-1", url="http://example.com")
        insert_snapshot(snapshot_id="snap-2", url="https://example.com")

        request = MockRequest()
        request.json_dat = {"url": "^http:\\/\\/example"}
        res, status = manager.query_snapshots(request)
        assert status == 200
        content = res["content"]
        assert content == [
            "snap-1",
        ]

    def test_query_empty_form(self, insert_snapshot, manager):
        insert_snapshot(snapshot_id="snap-1", start_time=100, end_time=102)
        insert_snapshot(snapshot_id="snap-2", start_time=103, end_time=104)
        insert_snapshot(snapshot_id="snap-3", start_time=104, end_time=104)
        insert_snapshot(snapshot_id="snap-4", start_time=105, end_time=106)
        request = MockRequest()
        request.json_dat = {}
        res, status = manager.query_snapshots(request)
        assert status == 200
        content = res["content"]
        assert content == ["snap-1", "snap-2", "snap-3", "snap-4"]


class TestQueryFiles:
    def test_query_no_filters(self, insert_snapshot, insert_file, manager):
        insert_snapshot(snapshot_id="snap-1", url="https://example.com")
        insert_snapshot(
            snapshot_id="snap-2",
            url="https://example.com",
            start_time=200,
            end_time=201,
        )

        insert_file(file_id="file-1", snapshot_id="snap-1")
        insert_file(file_id="file-2", snapshot_id="snap-1")
        insert_file(file_id="file-3", snapshot_id="snap-2")

        request = MockRequest()
        request.json_dat = {}

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
            },
        ]

    def test_query_snapshot_url_regex(
        self, insert_snapshot, insert_file, manager
    ):
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

        request = MockRequest()
        request.json_dat = {"url": "/index\\.html$"}

        res, status = manager.query_files(request)

        assert status == 200
        assert res["content"] == [
            {"snapshot_id": "snap-1", "file_id": "file-1"}
        ]

    def test_query_combined_filters(
        self, insert_snapshot, insert_file, manager
    ):
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

        request = MockRequest()
        request.json_dat = {
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
    def test_delete_not_exist(self, manager):
        resp, status = manager.delete_snapshot("snap-1")
        assert status == 404

    def test_delete_exist_has_files(
        self, tmp_path, monkeypatch, insert_snapshot, insert_file, manager
    ):
        monkeypatch.setattr("src.request_manager.base_dir", str(tmp_path))

        insert_snapshot(snapshot_id="snap-1")

        path = tmp_path / "snap-1" / "test.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"hello")

        insert_file(
            file_id="file-1", snapshot_id="snap-1", on_disk_path=str(path)
        )

        res, status = manager.delete_snapshot("snap-1")
        assert status == 202
        assert not path.exists()

        _, status2 = manager.get_file("file-1")
        assert status2 == 404

        _, status3 = manager.get_snapshot("snap-1")
        assert status3 == 404

    def test_delete_evil_path_no_remove(
        self, tmp_path, monkeypatch, insert_snapshot, insert_file, manager
    ):
        monkeypatch.setattr("src.request_manager.base_dir", str(tmp_path))

        request = MockRequest()
        request.json_dat = {"ids": [".", "/", "snap-1/../"]}

        insert_snapshot("snap-1")

        path1 = tmp_path / "snap-1" / "test.html"
        path1.parent.mkdir(parents=True, exist_ok=True)
        path1.write_bytes(b"test")

        insert_file(
            file_id="file-1", snapshot_id="snap-1", on_disk_path=str(path1)
        )

        res, status = manager.delete_snapshots(request)

        assert status == 202

        # IF the evil path was deleted, this should be gone too!
        assert path1.exists()
        res, status = manager.get_snapshot("snap-1")
        assert status == 200

    def test_delete_batch_snapshots(
        self, tmp_path, monkeypatch, insert_snapshot, insert_file, manager
    ):
        monkeypatch.setattr("src.request_manager.base_dir", str(tmp_path))

        request = MockRequest()
        request.json_dat = {"ids": ["snap-1", "snap-2", "snap-3"]}

        insert_snapshot("snap-1")
        insert_snapshot("snap-2")
        insert_snapshot("snap-3")

        path1 = tmp_path / "snap-1" / "3.html"
        path1.parent.mkdir(parents=True, exist_ok=True)
        path1.write_bytes(b"b")
        path2 = tmp_path / "snap-2" / "2.html"
        path2.parent.mkdir(parents=True, exist_ok=True)
        path2.write_bytes(b"b")

        insert_file(
            file_id="file-1", snapshot_id="snap-1", on_disk_path=str(path1)
        )
        insert_file(
            file_id="file-2", snapshot_id="snap-2", on_disk_path=str(path2)
        )

        res, status = manager.delete_snapshots(request)
        assert status == 202
        assert not path1.exists()
        assert not path2.exists()

        _, fstatus1 = manager.get_file("file-1")
        _, fstatus2 = manager.get_file("file-2")

        assert fstatus1 == 404
        assert fstatus2 == 404

        _, sstatus1 = manager.get_snapshot("snap-1")
        _, sstatus2 = manager.get_snapshot("snap-2")
        _, sstatus3 = manager.get_snapshot("snap-3")
        assert sstatus1 == 404
        assert sstatus2 == 404
        assert sstatus3 == 404

    def test_batch_delete_delete_fail(
        self, manager, insert_snapshot, insert_file, monkeypatch
    ):
        insert_snapshot(snapshot_id="snap-1")
        insert_file(snapshot_id="snap-1")
        manager.db.execute(
            """
            CREATE TRIGGER prevent_snapshot_delete
            BEFORE DELETE ON snapshots
            BEGIN
                SELECT RAISE(ABORT, 'born to fail');
            END;
            """,
        )

        request = MockRequest()
        request.json_dat = {"ids": ["snap-1"]}

        with patch.object(manager, "_delete_snapshot_files") as cleanup:
            resp, status = manager.delete_snapshots(request)

        assert status == 500
        assert not cleanup.called

        _, status = manager.get_snapshot("snap-1")
        assert status == 200

        # Logically guaranteed we do not touch the DB if we return a 400.
        with patch.object(manager, "_delete_snapshot_files") as cleanup:
            resp, status = manager.delete_snapshots(MockRequest())
        assert status == 400
        assert not cleanup.called


class TestProcessInterval:
    def test_process_single_interval(
        self, manager, insert_snapshot, insert_file, tmp_path
    ):
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
            file_size=os.path.getsize(file1),
            host="cdn.example.com",
        )
        insert_file(
            file_id="file-2",
            snapshot_id="snap-1",
            on_disk_path=str(file2),
            file_size=os.path.getsize(file2),
            host="cdn.example.com",
        )
        insert_file(
            file_id="file-3",
            snapshot_id="snap-2",
            on_disk_path=str(file3),
            file_size=os.path.getsize(file3),
            host="example.com",
        )
        interval = {
            "start": {"sec": 100, "nsec": 0},
            "end": {"sec": 200, "nsec": 0},
        }
        res, status = manager._process_interval(interval)
        assert status == 200
        assert res["snapshots"] == 2
        assert res["files"] == 3
        assert res["size"] == 9
        assert res["urls"] == 1
        assert res["hosts"] == 2

    def test_process_bad_interval(self, test_db):
        manager = RequestManager(test_db)

        interval = manager._build_interval(200, 100)
        res, status = manager._process_interval(interval)
        assert status == 400

    def test_process_no_results(self, manager):
        interval = manager._build_interval(100, 200)
        res, status = manager._process_interval(interval)
        assert status == 200
        assert res["snapshots"] == 0
        assert res["files"] == 0
        assert res["size"] == 0
        assert res["urls"] == 0
        assert res["hosts"] == 0


class TestGetLimits:
    def test_no_snaps(self, manager):
        res, status = manager.get_limits()
        assert status == 200
        assert res == {"first_snapshot": None, "last_snapshot": None}

    def test_get_right_snaps(self, manager, insert_snapshot):
        insert_snapshot(snapshot_id="snap-1", start_time=100)
        insert_snapshot(snapshot_id="snap-2", start_time=102)
        insert_snapshot(snapshot_id="snap-3", start_time=104)
        insert_snapshot(snapshot_id="snap-4", start_time=106)

        res, status = manager.get_limits()
        assert status == 200
        assert res == {
            "first_snapshot": manager._time_spec(100),
            "last_snapshot": manager._time_spec(106),
        }


class TestGetFileInfo:
    def test_get_file_info(self, manager, insert_snapshot, insert_file):
        insert_snapshot(snapshot_id="snap-1", start_time=100)
        insert_file(
            file_id="file-1",
            request_sent_time=100.0,
            request_method="GET",
            request_headers=json.dumps({"Authorization": ["Basic abc123"]}),
            request_parameters=json.dumps(
                {"param1": ["val"], "param2": ["val"]}
            ),
            response_recieved_time=101.0,
            response_code=200,
            response_headers=json.dumps(
                {"Content-Type": ["text/html"], "X-Factor": ["1000"]}
            ),
        )
        resp, status = manager.get_file_info("file-1")
        assert status == 200
        assert resp["id"] == "file-1"
        assert resp["snapshot"] == "snap-1"
        assert (
            resp["url"]
            == "/data/snap-1/https://example.com/index.html?param1=val&param2=val"
        )
        assert resp["protocol"] == "https"
        assert resp["port"] == 443
        assert resp["host"] == "example.com"
        assert resp["path"] == "index.html"
        assert resp["request"] == {
            "sent_time": {"sec": 100, "nsec": 0},
            "method": "GET",
            "headers": {"Authorization": ["Basic abc123"]},
            "parameters": {
                "param1": ["val"],
                "param2": ["val"],
            },
        }
        assert resp["response"] == {
            "recieved_time": {"sec": 101, "nsec": 0},
            "code": 200,
            "headers": {"Content-Type": ["text/html"], "X-Factor": ["1000"]},
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

    def test_query_snapshot(self, insert_snapshot):
        self.setup()
        insert_snapshot(snapshot_id="snap-1", start_time=400)

        body = {"start_time": {"sec": 300, "nsec": 0}}
        resp = self.client.open(
            "/search/snapshots", method="QUERY", json={"host": "example.com"}
        )
        assert resp.status_code == 200

        assert resp.json is not None
        assert resp.get_json()[0] == "snap-1"

    def test_delete_snapshot(self, insert_snapshot):
        self.setup()
        insert_snapshot(snapshot_id="snap-1")

        resp = self.client.delete("/snapshots/snap-1")
        assert resp.status_code == 202

        resp2 = self.client.delete("/snapshots/snap-2")
        assert resp2.status_code == 404

    def test_delete_snapshots(self, insert_snapshot):
        self.setup()
        insert_snapshot(snapshot_id="snap-1")
        insert_snapshot(snapshot_id="snap-2")

        body = {"ids": ["snap-1", "snap-2"]}

        resp = self.client.post("snapshots/delete", json=body)
        assert resp.status_code == 202

        resp = self.client.delete("snapshots/snap-1")
        assert resp.status_code == 404

    def test_create_bookmark_route(self, insert_snapshot):
        self.setup()
        insert_snapshot(snapshot_id="snap-1")
        body = {
            "name": "Test Bookmark",
            "snapshot_id": "snap-1",
        }
        resp = self.client.post("/bookmarks/create", json=body)
        assert resp.status_code == 201
        assert "id" in resp.json  # type: ignore[operator]

    def test_create_bookmark_route_missing_name(self, insert_snapshot):
        self.setup()
        insert_snapshot(snapshot_id="snap-1")
        body = {
            "snapshot_id": "snap-1",
        }
        resp = self.client.post("/bookmarks/create", json=body)
        assert resp.status_code == 400

    def test_search_bookmarks_route(self, insert_snapshot):
        self.setup()
        insert_snapshot(snapshot_id="snap-1")
        # Create a bookmark via the API
        body = {
            "name": "Test Bookmark",
            "snapshot_id": "snap-1",
        }
        resp = self.client.post("/bookmarks/create", json=body)
        assert resp.status_code == 201
        bookmark_id = resp.json["id"]  # type: ignore[index]

        # Search for it
        search_body = {"name": "Test Bookmark"}
        resp2 = self.client.open(
            "/search/bookmarks",
            method="QUERY",
            json=search_body,
        )
        assert resp2.status_code == 200

    def test_delete_bookmark_route(self, insert_snapshot):
        self.setup()
        insert_snapshot(snapshot_id="snap-1")
        # Create a bookmark via the API
        body = {
            "name": "Test Bookmark",
            "snapshot_id": "snap-1",
        }
        resp = self.client.post("/bookmarks/create", json=body)
        assert resp.status_code == 201
        bookmark_id = resp.json["id"]  # type: ignore[index]

        # Delete it
        resp2 = self.client.delete(f"/bookmarks/{bookmark_id}")
        assert resp2.status_code == 202

    def test_delete_bookmark_route_not_found(self, insert_snapshot):
        self.setup()
        insert_snapshot(snapshot_id="snap-1")
        # Try to delete nonexistent
        resp = self.client.delete("/bookmarks/nonexistent")
        assert resp.status_code == 404


class Task_4_5_1_TestCreateBookmark:
    def test_create_snapshot_bookmark(self, manager, insert_snapshot):
        insert_snapshot(snapshot_id="snap-1")
        request = MockRequest()
        request.json_dat = {
            "name": "My Snapshot Bookmark",
            "snapshot_id": "snap-1",
        }
        resp, status = manager.create_bookmark(request)

        assert status == 201
        assert "id" in resp
        assert isinstance(resp["id"], str)

        # Verify in database
        row = manager.db.execute(
            "SELECT name, snapshot_id, file_id FROM bookmarks WHERE id = ?",
            (resp["id"],),
        ).fetchone()
        assert row is not None
        assert row[0] == "My Snapshot Bookmark"
        assert row[1] == "snap-1"
        assert row[2] is None

    def test_create_file_bookmark(self, manager, insert_snapshot, insert_file):
        insert_snapshot(snapshot_id="snap-1")
        insert_file(file_id="file-1", snapshot_id="snap-1")
        request = MockRequest()
        request.json_dat = {
            "name": "My File Bookmark",
            "file_id": "file-1",
        }
        resp, status = manager.create_bookmark(request)

        assert status == 201
        assert "id" in resp

        row = manager.db.execute(
            "SELECT name, snapshot_id, file_id FROM bookmarks WHERE id = ?",
            (resp["id"],),
        ).fetchone()
        assert row is not None
        assert row[0] == "My File Bookmark"
        assert row[1] is None
        assert row[2] == "file-1"

    def test_create_bookmark_missing_name(self, manager):
        request = MockRequest()
        request.json_dat = {
            "snapshot_id": "snap-1",
        }
        resp, status = manager.create_bookmark(request)
        assert status == 400
        assert "message" in resp

    def test_create_bookmark_both_ids(
        self, manager, insert_snapshot, insert_file
    ):
        insert_snapshot(snapshot_id="snap-1")
        insert_file(file_id="file-1", snapshot_id="snap-1")
        request = MockRequest()
        request.json_dat = {
            "name": "Bad Bookmark",
            "snapshot_id": "snap-1",
            "file_id": "file-1",
        }
        resp, status = manager.create_bookmark(request)
        assert status == 400

    def test_create_bookmark_neither_id(self, manager):
        request = MockRequest()
        request.json_dat = {
            "name": "Bad Bookmark",
        }
        resp, status = manager.create_bookmark(request)
        assert status == 400

    def test_create_bookmark_name_not_string(self, manager, insert_snapshot):
        """Test that non-string name returns 400"""
        insert_snapshot(snapshot_id="snap-1")
        request = MockRequest()
        request.json_dat = {
            "name": 123,  # integer instead of string
            "snapshot_id": "snap-1",
        }
        resp, status = manager.create_bookmark(request)
        assert status == 400
        assert "name" in resp["message"].lower()

    def test_create_bookmark_name_null(self, manager, insert_snapshot):
        """Test that null name returns 400"""
        insert_snapshot(snapshot_id="snap-1")
        request = MockRequest()
        request.json_dat = {
            "name": None,
            "snapshot_id": "snap-1",
        }
        resp, status = manager.create_bookmark(request)
        assert status == 400

    def test_create_bookmark_file_id_not_string(
        self, manager, insert_snapshot
    ):
        """Test that non-string file_id returns 400"""
        insert_snapshot(snapshot_id="snap-1")
        request = MockRequest()
        request.json_dat = {
            "name": "Test",
            "file_id": 123,  # integer instead of string
        }
        resp, status = manager.create_bookmark(request)
        assert status == 400

    def test_create_bookmark_empty_name(self, manager, insert_snapshot):
        """Test that empty string name is accepted"""
        insert_snapshot(snapshot_id="snap-1")
        request = MockRequest()
        request.json_dat = {
            "name": "",
            "snapshot_id": "snap-1",
        }
        resp, status = manager.create_bookmark(request)
        assert status == 201
        assert "id" in resp

    def test_create_bookmark_invalid_snapshot_fails(self, manager):
        request = MockRequest()
        request.json_dat = {
            "name": "Bad Bookmark",
            "snapshot_id": "nonexistent-snapshot",
        }
        resp, status = manager.create_bookmark(request)
        assert status == 400

    def test_create_bookmark_invalid_file_fails(
        self, manager, insert_snapshot
    ):
        insert_snapshot(snapshot_id="snap-1")
        request = MockRequest()
        request.json_dat = {
            "name": "Bad Bookmark",
            "file_id": "nonexistent-file",
        }
        resp, status = manager.create_bookmark(request)
        assert status == 400


class Task_4_5_1_TestQueryBookmarks:
    def test_query_by_id(self, manager, insert_snapshot):
        insert_snapshot(snapshot_id="snap-1")
        request = MockRequest()
        request.json_dat = {
            "name": "Bookmark 1",
            "snapshot_id": "snap-1",
        }
        resp, status = manager.create_bookmark(request)
        bookmark_id = resp["id"]

        request2 = MockRequest()
        request2.json_dat = {"id": bookmark_id}
        result, status = manager.query_bookmarks(request2)
        assert status == 200
        assert result == [bookmark_id]

    def test_query_by_name(self, manager, insert_snapshot):
        insert_snapshot(snapshot_id="snap-1")
        insert_snapshot(snapshot_id="snap-2")

        request = MockRequest()
        request.json_dat = {
            "name": "Unique Name",
            "snapshot_id": "snap-1",
        }
        manager.create_bookmark(request)

        request2 = MockRequest()
        request2.json_dat = {
            "name": "Other Name",
            "snapshot_id": "snap-2",
        }
        manager.create_bookmark(request2)

        request3 = MockRequest()
        request3.json_dat = {"name": "Unique Name"}
        result, status = manager.query_bookmarks(request3)
        assert status == 200
        assert len(result) == 1

    def test_query_by_snapshot_id(self, manager, insert_snapshot):
        insert_snapshot(snapshot_id="snap-1")
        insert_snapshot(snapshot_id="snap-2")

        request = MockRequest()
        request.json_dat = {
            "name": "Bookmark 1",
            "snapshot_id": "snap-1",
        }
        resp1, _ = manager.create_bookmark(request)

        request2 = MockRequest()
        request2.json_dat = {
            "name": "Bookmark 2",
            "snapshot_id": "snap-2",
        }
        resp2, _ = manager.create_bookmark(request2)

        request3 = MockRequest()
        request3.json_dat = {"snapshot_id": "snap-1"}
        result, status = manager.query_bookmarks(request3)
        assert status == 200
        assert result == [resp1["id"]]

    def test_query_by_file_id(self, manager, insert_snapshot, insert_file):
        insert_snapshot(snapshot_id="snap-1")
        insert_file(file_id="file-1", snapshot_id="snap-1")
        insert_file(file_id="file-2", snapshot_id="snap-1")

        request = MockRequest()
        request.json_dat = {
            "name": "Bookmark 1",
            "file_id": "file-1",
        }
        resp1, _ = manager.create_bookmark(request)

        request2 = MockRequest()
        request2.json_dat = {
            "name": "Bookmark 2",
            "file_id": "file-2",
        }
        resp2, _ = manager.create_bookmark(request2)

        request3 = MockRequest()
        request3.json_dat = {"file_id": "file-1"}
        result, status = manager.query_bookmarks(request3)
        assert status == 200
        assert result == [resp1["id"]]

    def test_query_no_filters_returns_all(self, manager, insert_snapshot):
        insert_snapshot(snapshot_id="snap-1")

        request = MockRequest()
        request.json_dat = {
            "name": "Bookmark 1",
            "snapshot_id": "snap-1",
        }
        resp1, _ = manager.create_bookmark(request)

        request2 = MockRequest()
        request2.json_dat = {
            "name": "Bookmark 2",
            "snapshot_id": "snap-1",
        }
        resp2, _ = manager.create_bookmark(request2)

        request3 = MockRequest()
        request3.json_dat = {}
        result, status = manager.query_bookmarks(request3)
        assert status == 200
        assert set(result) == {resp1["id"], resp2["id"]}

    def test_query_no_matches_returns_empty(self, manager, insert_snapshot):
        insert_snapshot(snapshot_id="snap-1")

        request = MockRequest()
        request.json_dat = {"name": "nonexistent"}
        result, status = manager.query_bookmarks(request)
        assert status == 200
        assert result == []

    def test_query_empty_string_name_matches_all(
        self, manager, insert_snapshot
    ):
        """Test that empty string name matches all bookmarks (regex behavior)"""
        insert_snapshot(snapshot_id="snap-1")

        # Create multiple bookmarks
        for i in range(3):
            req = MockRequest()
            req.json_dat = {"name": f"Bookmark {i}", "snapshot_id": "snap-1"}
            manager.create_bookmark(req)

        # Query with empty string - should match all
        request = MockRequest()
        request.json_dat = {"name": ""}
        result, status = manager.query_bookmarks(request)
        assert status == 200
        assert len(result) == 3

    def test_query_name_not_string(self, manager, insert_snapshot):
        """Test that non-string name filter returns 400"""
        insert_snapshot(snapshot_id="snap-1")

        request = MockRequest()
        request.json_dat = {"name": 123}  # integer instead of string
        result, status = manager.query_bookmarks(request)
        assert status == 400

    def test_query_by_name_regex(self, manager, insert_snapshot):
        insert_snapshot(snapshot_id="snap-1")

        # Create bookmarks with similar names
        request = MockRequest()
        request.json_dat = {
            "name": "Project Alpha",
            "snapshot_id": "snap-1",
        }
        resp1, _ = manager.create_bookmark(request)

        request2 = MockRequest()
        request2.json_dat = {
            "name": "Project Beta",
            "snapshot_id": "snap-1",
        }
        resp2, _ = manager.create_bookmark(request2)

        # Search using regex pattern that should match both
        request3 = MockRequest()
        request3.json_dat = {"name": r"^Project (Alpha|Beta)$"}
        result, status = manager.query_bookmarks(request3)
        assert status == 200
        assert set(result) == {resp1["id"], resp2["id"]}

    def test_query_combined_filters(
        self, manager, insert_snapshot, insert_file
    ):
        insert_snapshot(snapshot_id="snap-1")
        insert_snapshot(snapshot_id="snap-2")
        insert_file(file_id="file-1", snapshot_id="snap-1")

        # Create bookmarks
        request = MockRequest()
        request.json_dat = {
            "name": "Bookmark 1",
            "snapshot_id": "snap-1",
        }
        resp1, _ = manager.create_bookmark(request)

        request2 = MockRequest()
        request2.json_dat = {
            "name": "Bookmark 2",
            "file_id": "file-1",
        }
        resp2, _ = manager.create_bookmark(request2)

        request3 = MockRequest()
        request3.json_dat = {
            "name": "Bookmark 2",
            "snapshot_id": "snap-2",  # This bookmark has file_id, not snapshot_id
        }
        result, status = manager.query_bookmarks(request3)
        assert status == 200
        assert result == []


class Task_4_5_1_TestDeleteBookmark:
    def test_delete_existing_bookmark(self, manager, insert_snapshot):
        insert_snapshot(snapshot_id="snap-1")

        # Create a bookmark
        request = MockRequest()
        request.json_dat = {
            "name": "Test Bookmark",
            "snapshot_id": "snap-1",
        }
        resp, status = manager.create_bookmark(request)
        bookmark_id = resp["id"]

        # Try to delete it
        result, status = manager.delete_bookmark(bookmark_id)
        assert status == 202

        # Verify it's gone from DB
        row = manager.db.execute(
            "SELECT * FROM bookmarks WHERE id = ?",
            (bookmark_id,),
        ).fetchone()
        assert row is None

    def test_delete_nonexistent_bookmark(self, manager):
        result, status = manager.delete_bookmark("nonexistent-id")
        assert status == 404

    def test_delete_only_target_bookmark(self, manager, insert_snapshot):
        insert_snapshot(snapshot_id="snap-1")

        # Create multiple bookmarks
        request1 = MockRequest()
        request1.json_dat = {
            "name": "Bookmark 1",
            "snapshot_id": "snap-1",
        }
        resp1, _ = manager.create_bookmark(request1)

        request2 = MockRequest()
        request2.json_dat = {
            "name": "Bookmark 2",
            "snapshot_id": "snap-1",
        }
        resp2, _ = manager.create_bookmark(request2)

        # Delete one
        manager.delete_bookmark(resp1["id"])

        # Verify the other one still exists
        row = manager.db.execute(
            "SELECT * FROM bookmarks WHERE id = ?",
            (resp2["id"],),
        ).fetchone()
        assert row is not None


class TestInvalidRegexpPatterns:
    def test_invalid_regex_in_query_bookmarks(self, manager, insert_snapshot):
        """Test that invalid regex patterns return 400 Bad Request"""
        insert_snapshot(snapshot_id="snap-1")

        request = MockRequest()
        request.json_dat = {"name": "[invalid regex"}
        result, status = manager.query_bookmarks(request)
        assert status == 400
        assert "invalid regexp" in result["message"].lower()

    def test_unbalanced_parenthesis_regex(self, manager, insert_snapshot):
        """Test unbalanced parenthesis in regex pattern"""
        insert_snapshot(snapshot_id="snap-1")

        request = MockRequest()
        request.json_dat = {"name": "test(unclosed"}
        result, status = manager.query_bookmarks(request)
        assert status == 400

    def test_invalid_repeat_regex(self, manager, insert_snapshot):
        """Test invalid repeat in regex pattern"""
        insert_snapshot(snapshot_id="snap-1")

        request = MockRequest()
        request.json_dat = {"name": "+test"}
        result, status = manager.query_bookmarks(request)
        assert status == 400


class TestConcurrentAccess:
    def test_concurrent_create_bookmarks(
        self, test_db, manager, insert_snapshot
    ):
        """Test that concurrent bookmark creation works correctly"""

        insert_snapshot(snapshot_id="snap-1")

        def create_bookmark(name):
            req = MockRequest()
            req.json_dat = {"name": name, "snapshot_id": "snap-1"}
            with RequestManager(test_db) as manager:
                _, status = manager.create_bookmark(req)
            return status

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(create_bookmark, f"Bookmark {i}")
                for i in range(10)
            ]
            results = [
                f.result() for f in concurrent.futures.as_completed(futures)
            ]

        assert all(status == 201 for status in results)

        # Verify all bookmarks were created
        count = manager.db.execute(
            "SELECT COUNT(*) FROM bookmarks"
        ).fetchone()[0]
        assert count == 10

    def test_concurrent_query_and_create(
        self, test_db, manager, insert_snapshot
    ):
        """Test concurrent reading and writing"""
        import threading
        import concurrent.futures

        insert_snapshot(snapshot_id="snap-1")

        # Create some bookmarks first
        for i in range(5):
            req = MockRequest()
            req.json_dat = {"name": f"Existing {i}", "snapshot_id": "snap-1"}
            manager.create_bookmark(req)

        results = []
        errors = []

        def reader():
            try:
                req = MockRequest()
                req.json_dat = {}
                with RequestManager(test_db) as manager:
                    result, status = manager.query_bookmarks(req)
                results.append(status)
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                req = MockRequest()
                req.json_dat = {"name": "New", "snapshot_id": "snap-1"}
                with RequestManager(test_db) as manager:
                    result, status = manager.create_bookmark(req)
                results.append(status)
            except Exception as e:
                errors.append(e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(reader) for _ in range(5)] + [
                executor.submit(writer) for _ in range(5)
            ]
            concurrent.futures.wait(futures)

        assert len(errors) == 0
        assert all(status in (200, 201) for status in results)


class TestErrorHandling:
    def test_create_bookmark_db_error(self, manager, insert_snapshot):
        """Test that database errors during create are handled gracefully"""
        insert_snapshot(snapshot_id="snap-1")
        manager.db = MagicMock(wraps=manager.db)

        # Mock db.execute to raise an exception
        def mock_execute(*args, **kwargs):
            raise sqlite3.OperationalError("database is locked")

        manager.db.execute = mock_execute

        request = MockRequest()
        request.json_dat = {"name": "Test", "snapshot_id": "snap-1"}
        result, status = manager.create_bookmark(request)

        assert status == 500
        assert "unexpected error" in result["message"].lower()

    def test_query_bookmarks_db_error(self, manager, insert_snapshot):
        """Test that database errors during query are handled gracefully"""
        insert_snapshot(snapshot_id="snap-1")
        manager.db = MagicMock(wraps=manager.db)

        # Mock db.execute to raise an exception
        def mock_execute(*args, **kwargs):
            raise sqlite3.OperationalError("database is locked")

        manager.db.execute = mock_execute

        request = MockRequest()
        request.json_dat = {"name": "Test"}
        result, status = manager.query_bookmarks(request)

        assert status == 500
        assert "unexpected error" in result["message"].lower()

    def test_delete_bookmark_db_error(self, manager, insert_snapshot):
        """Test that database errors during delete are handled gracefully"""
        insert_snapshot(snapshot_id="snap-1")
        manager.db = MagicMock(wraps=manager.db)

        # Create a bookmark first
        request = MockRequest()
        request.json_dat = {"name": "Test", "snapshot_id": "snap-1"}
        resp, status = manager.create_bookmark(request)
        bookmark_id = resp["id"]

        # Mock db.execute to raise an exception
        def mock_execute(*args, **kwargs):
            raise sqlite3.OperationalError("database is locked")

        manager.db.execute = mock_execute

        result, status = manager.delete_bookmark(bookmark_id)

        assert status == 500
        assert "unexpected error" in result["message"].lower()

    def test_create_bookmark_foreign_key_error(self, manager):
        """Test that foreign key constraint violations are handled"""
        request = MockRequest()
        request.json_dat = {"name": "Test", "snapshot_id": "nonexistent"}
        result, status = manager.create_bookmark(request)

        assert status == 400
        assert "non-existent" in result["message"].lower()

    def test_create_bookmark_invalid_payload(self, manager):
        """Test that invalid JSON payloads are handled"""

        # Create a request object that returns non-dict
        class InvalidRequest:
            def get_json(self, silent=False):
                return "not a dict"

        request = InvalidRequest()
        result, status = manager.create_bookmark(request)

        assert status == 400
        assert "json" in result["message"].lower()

    def test_query_bookmarks_invalid_payload(self, manager):
        """Test that invalid JSON payloads are handled"""

        class InvalidRequest:
            def get_json(self, silent=False):
                return "not a dict"

        request = InvalidRequest()
        result, status = manager.query_bookmarks(request)

        assert status == 400
