"""Exercise the scraper's response handler against a real recovery server."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from pathlib import Path
import sqlite3
from threading import Thread
from types import SimpleNamespace
from urllib.parse import urljoin, urlsplit
from unittest.mock import AsyncMock

from bs4 import BeautifulSoup
from flask import Flask, request
import pytest

from src.request_manager import RequestManager
from src.scraping import scraper as scraper_module
from src.urlreplace import relativize_html


VIDEO = bytes(range(128))
MIDDLE = VIDEO[32:64]
PARTIAL_RANGE = "bytes 32-63/128"


@pytest.fixture
def video_origin():
    class VideoSite(BaseHTTPRequestHandler):
        def do_GET(self):
            self.server.requests.append(self.headers)
            mode = urlsplit(self.path).path.rsplit("/", 1)[-1]
            content_type = (
                "video/mp4" if mode.endswith(".mp4") or mode.startswith("mp4-")
                else "video/webm"
            )
            never_complete = mode.startswith("partial") or self.headers.get("Range")
            body = MIDDLE if never_complete else VIDEO
            self.send_response(206 if never_complete else 200)
            if never_complete:
                self.send_header("Content-Range", PARTIAL_RANGE)
            self.send_header("Content-Type", content_type)
            if not mode.startswith("no-length"):
                self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), VideoSite) as server:
        server.requests = []
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", server.requests
        finally:
            server.shutdown()
            thread.join()


@pytest.fixture
def capture(tmp_path, monkeypatch):
    with sqlite3.connect(":memory:") as db:
        schema = Path(__file__).resolve().parents[1] / "db" / "001_init.sql"
        db.executescript(schema.read_text())
        db.execute("INSERT INTO snapshots VALUES ('snap', 'https://example.org', 1, 1)")
        scraper = scraper_module.PageScraper(db_conn=db)
        scraper.snap_id = "snap"
        monkeypatch.setattr(scraper, "get_base_dir", lambda _url: str(tmp_path))
        scraper.set_origin_url("http://127.0.0.1/index.html")
        scraper.tasks = []
        yield scraper, db, tmp_path


def record_response(scraper, url, mime, body, content_range=None):
    request = SimpleNamespace(
        url=url, method="GET",
        headers_array=AsyncMock(return_value=[
            {"name": "range", "value": "bytes=32-63"},
            {"name": "referer", "value": "https://example.org/"},
        ]),
    )
    headers = {"content-type": mime, "content-length": str(len(body))}
    if content_range:
        headers["content-range"] = content_range
    response = SimpleNamespace(
        url=url, request=request, status=206 if content_range else 200,
        all_headers=AsyncMock(return_value=headers),
        headers_array=AsyncMock(return_value=[
            {"name": name, "value": value} for name, value in headers.items()
        ]),
        body=AsyncMock(return_value=body),
    )
    scraper.handle_requests(request)
    scraper.on_response(response)


def saved_files(db):
    return db.execute(
        "SELECT on_disk_path, file_size, response_code, json(response_headers) FROM files"
    ).fetchall()


def assert_saved_video(db, expected_status):
    [(path, size, status, raw_headers)] = saved_files(db)
    assert status == expected_status
    assert size == len(VIDEO)
    assert Path(path).read_bytes() == VIDEO
    return json.loads(raw_headers)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "site,path,subtype",
    [
        ("127.0.0.1", "/mp4-delivery?id=42", "mp4"),
        ("example.org", "/mp4-delivery?id=42", "mp4"),
        ("example.org", "/webm-delivery/", "webm"),
    ],
)
async def test_3_4_1_archives_extensionless_video_and_replays_by_original_url(
    capture, video_origin, site, path, subtype
):
    scraper, db, _ = capture
    origin, requests = video_origin
    scraper.set_origin_url(f"http://{site}/index.html")
    url = origin + path
    mime = f"video/{subtype}"
    record_response(scraper, url, mime, MIDDLE, PARTIAL_RANGE)
    await scraper._drain_tasks()

    assert len(requests) == 1
    assert_saved_video(db, 200)
    [(location, *_)] = saved_files(db)
    assert Path(location).suffix == f".{subtype}"
    page_url = f"http://{site}/index.html"
    markup = relativize_html(f'<video controls src="{url}"></video>', page_url)
    source = BeautifulSoup(markup, "html.parser").video["src"]
    replay_url = urlsplit(urljoin("http://127.0.0.1:3000/data/snap/" + page_url, source))
    with Flask(__name__).test_request_context(query_string=replay_url.query):
        response, status = RequestManager(db).get_file_by_url(
            "snap", replay_url.path.removeprefix("/data/snap/"), request
        )
    assert status == 200
    assert response["body"] == VIDEO
    assert response["content_type"] == mime


@pytest.mark.asyncio
async def test_3_4_1_inferred_video_names_do_not_overwrite_existing_urls(capture):
    scraper, db, _ = capture
    urls = [
        "http://127.0.0.1/video",
        "http://127.0.0.1/video.mp4",
        "http://127.0.0.1/video?quality=high",
        "http://127.0.0.1/video/",
        "http://127.0.0.1/video/index.mp4",
    ]
    for index, url in enumerate(urls):
        body = bytes([index])
        record_response(scraper, url, "video/mp4", body)
        await scraper._drain_tasks()
        assert Path(scraper.saved_resources[url]["path"]).read_bytes() == body

    paths = [Path(path) for path, *_ in saved_files(db)]
    assert len(set(paths)) == len(urls)
    assert {p.read_bytes() for p in paths} == {bytes([i]) for i in range(len(urls))}
    assert all(p.suffix == ".mp4" for p in paths)


@pytest.mark.asyncio
@pytest.mark.parametrize("content_range,status", [(None, 200), ("bytes 0-127/128", 206)])
async def test_3_4_1_saves_complete_video_without_retry(capture, video_origin, content_range, status, caplog):
    scraper, db, _ = capture
    origin, requests = video_origin
    record_response(scraper, origin + "/full.mp4", "video/mp4", VIDEO, content_range)
    with caplog.at_level(logging.DEBUG, logger=scraper_module.__name__):
        await scraper._drain_tasks()

    assert_saved_video(db, status)
    assert requests == []
    assert "Response body read for" in caplog.text
    assert "Full video recovery for" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("subtype", ["mp4", "webm"])
async def test_3_4_1_recovers_one_complete_video_from_concurrent_ranges(capture, video_origin, subtype, caplog):
    scraper, db, _ = capture
    origin, requests = video_origin
    url = f"{origin}/retry.{subtype}"
    for _ in range(3):
        record_response(scraper, url, f"video/{subtype}", MIDDLE, PARTIAL_RANGE)
    with caplog.at_level(logging.DEBUG, logger=scraper_module.__name__):
        await scraper._drain_tasks()

    headers = assert_saved_video(db, 200)
    assert "content-range" not in headers
    assert headers["content-length"] == [str(len(VIDEO))]
    [request] = requests
    assert "Range" not in request
    assert request["Referer"] == "https://example.org/"
    assert f"Full video recovery for {url} took" in caplog.text


@pytest.mark.asyncio
async def test_3_4_1_skips_a_video_if_the_retry_is_partial(capture, video_origin, caplog):
    scraper, db, root = capture
    origin, requests = video_origin
    url = origin + "/partial.webm"
    record_response(scraper, url, "video/webm", MIDDLE, PARTIAL_RANGE)
    await scraper._drain_tasks()
    record_response(scraper, url, "video/webm", MIDDLE, PARTIAL_RANGE)
    await scraper._drain_tasks()

    [request] = requests
    assert "Range" not in request
    assert saved_files(db) == []
    assert db.execute("SELECT id FROM snapshots").fetchall() == [("snap",)]
    assert not list(root.rglob("*.webm"))
    assert "Could not save the complete video" in caplog.text


@pytest.mark.asyncio
async def test_3_4_1_bounds_retry_without_a_declared_size(capture, video_origin, monkeypatch, caplog):
    scraper, db, root = capture
    origin, requests = video_origin
    monkeypatch.setattr(scraper_module, "VIDEO_RECOVERY_MAX_BYTES", 64)
    record_response(scraper, origin + "/no-length.webm", "video/webm", MIDDLE, "bytes 32-63/*")
    await scraper._drain_tasks()

    assert len(requests) == 1
    assert saved_files(db) == []
    assert not list(root.rglob("*.webm"))
    assert "Could not save the complete video" in caplog.text
