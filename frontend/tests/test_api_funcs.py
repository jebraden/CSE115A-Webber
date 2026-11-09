# Note: tests the API functions with the exception of statistics(), as that's tested in another file
import pytest
import asyncio
import json
import httpx

from src.api import (
    APIError,
    InternalServerError,
    NotFoundError,
    BadRequestError,
    BadResponseError,
    UnknownAPIError,
    CreateSnapshotResponse,
    FileQueryResponse,
    GetFileResponse,
    GetSnapshotResponse,
    SnapshotQueryResponse,
    Timespec,
    WebberAPI,
)

BASE = "http://backend"


def run(coro):
    return asyncio.run(coro)


###############
# Test helpers #
###############
class FakeBackend:
    """Holds the canned response and records every request made."""

    def __init__(self):
        self.response = httpx.Response(200, json={})
        self.calls: list[dict] = []

    def respond(self, status: int, body=None, *, raw: str | None = None):
        """Set the next response: JSON `body`, or `raw` text (e.g. invalid JSON)."""
        if raw is not None:
            self.response = httpx.Response(status, content=raw.encode())
        else:
            self.response = httpx.Response(status, json=body if body is not None else {})

    @property
    def last(self) -> dict:
        return self.calls[-1]


@pytest.fixture
def backend(monkeypatch) -> FakeBackend:
    state = FakeBackend()

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def request(self, method, url, content=None):
            state.calls.append({"method": method, "url": url, "content": content})
            return state.response

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    return state


@pytest.fixture
def api() -> WebberAPI:
    # trailing slash on purpose: urls below must not contain a double slash
    return WebberAPI(BASE + "/")


###################
# create_snapshot #
###################
class TestCreateSnapshot:
    def test_success_returns_id(self, api, backend):
        backend.respond(201, {"id": "snap-123"})

        result = run(api.create_snapshot("http://example.com"))

        assert isinstance(result, CreateSnapshotResponse)
        assert result.id == "snap-123"

    def test_request_url_and_body(self, api, backend):
        backend.respond(201, {"id": "snap-123"})

        run(api.create_snapshot("http://example.com"))

        assert backend.last["url"] == f"{BASE}/snapshots/create"
        assert backend.last["content"] == json.dumps("http://example.com").encode()

    def test_uses_post(self, api, backend):
        # NOTE: the docstring says POST, but the implementation currently sends
        # GET. This test follows the documented behavior.
        backend.respond(201, {"id": "snap-123"})

        run(api.create_snapshot("http://example.com"))

        assert backend.last["method"] == "POST"

    def test_bad_request_raises_bad_request_error(self, api, backend):
        backend.respond(400, {"message": "invalid url"})

        with pytest.raises(BadRequestError) as exc:
            run(api.create_snapshot("nonsense"))

        assert str(exc.value) == "invalid url"
        assert exc.value.code == 400

    def test_server_error_raises_internal_server_error(self, api, backend):
        backend.respond(500, {"message": "boom"})

        with pytest.raises(InternalServerError) as exc:
            run(api.create_snapshot("http://example.com"))

        assert str(exc.value) == "boom"

    def test_unexpected_status_raises_unknown_api_error(self, api, backend):
        backend.respond(503, raw="service unavailable")

        with pytest.raises(UnknownAPIError) as exc:
            run(api.create_snapshot("http://example.com"))

        assert exc.value.code == 503
        assert exc.value.body == "service unavailable"

    def test_200_is_not_accepted_as_success(self, api, backend):
        # the endpoint is specified to return 201
        backend.respond(200, {"id": "snap-123"})

        with pytest.raises(APIError):
            run(api.create_snapshot("http://example.com"))

    def test_invalid_json_raises_bad_response_error(self, api, backend):
        backend.respond(201, raw="not json")

        with pytest.raises(BadResponseError):
            run(api.create_snapshot("http://example.com"))

    def test_missing_id_raises_bad_response_error(self, api, backend):
        backend.respond(201, {"something_else": 1})

        with pytest.raises(BadResponseError):
            run(api.create_snapshot("http://example.com"))


###################
# delete_snapshot #
###################
class TestDeleteSnapshot:
    def test_202_returns_true(self, api, backend):
        backend.respond(202, {})

        assert run(api.delete_snapshot("snap-1")) is True

    def test_request_method_and_url(self, api, backend):
        backend.respond(202, {})

        run(api.delete_snapshot("snap-1"))

        assert backend.last["method"] == "DELETE"
        assert backend.last["url"] == f"{BASE}/snapshots/snap-1"

    @pytest.mark.parametrize("status", [200, 204, 400, 404, 500])
    def test_other_statuses_return_false(self, api, backend, status):
        backend.respond(status, {})

        assert run(api.delete_snapshot("snap-1")) is False


################
# get_snapshot #
################
SNAPSHOT_BODY = {
    "id": "snap-1",
    "url": "http://example.com",
    "start_time": {"sec": 10, "nsec": 20},
    "end_time": {"sec": 30, "nsec": 40},
    "files": ["f1", "f2"],
}


class TestGetSnapshot:
    def test_success(self, api, backend):
        backend.respond(200, SNAPSHOT_BODY)

        result = run(api.get_snapshot("snap-1"))

        assert isinstance(result, GetSnapshotResponse)
        assert result.id == "snap-1"
        assert result.url == "http://example.com"
        assert result.start_time == Timespec(10, 20)
        assert result.end_time == Timespec(30, 40)
        assert list(result.files) == ["f1", "f2"]

    def test_request_method_and_url(self, api, backend):
        backend.respond(200, SNAPSHOT_BODY)

        run(api.get_snapshot("snap-1"))

        assert backend.last["method"] == "GET"
        assert backend.last["url"] == f"{BASE}/snapshots/snap-1"

    def test_not_found(self, api, backend):
        backend.respond(404, {"message": "no such snapshot"})

        with pytest.raises(NotFoundError) as exc:
            run(api.get_snapshot("missing"))

        assert str(exc.value) == "no such snapshot"
        assert exc.value.code == 404

    def test_server_error(self, api, backend):
        backend.respond(500, {"message": "boom"})

        with pytest.raises(InternalServerError):
            run(api.get_snapshot("snap-1"))

    def test_invalid_json_raises_bad_response_error(self, api, backend):
        backend.respond(200, raw="<html>oops</html>")

        with pytest.raises(BadResponseError):
            run(api.get_snapshot("snap-1"))

    def test_body_missing_fields_raises_bad_response_error(self, api, backend):
        backend.respond(200, {"id": "snap-1"})

        with pytest.raises(BadResponseError):
            run(api.get_snapshot("snap-1"))


############
# get_file #
############
FILE_BODY = {
    "id": "file-1",
    "snapshot": "snap-1",
    "url": "http://example.com/index.html",
    "protocol": "http",
    "port": 80,
    "host": "example.com",
    "path": "/index.html",
    "request": {
        "sent_time": {"sec": 1, "nsec": 2},
        "method": "GET",
        "headers": {"Accept": ["*/*"]},
        "parameters": {"q": ["1"]},
    },
    "response": {
        "received_time": {"sec": 3, "nsec": 4},
        "code": 200,
        "headers": {"Content-Type": ["text/html"]},
    },
}


class TestGetFile:
    def test_success(self, api, backend):
        backend.respond(200, FILE_BODY)

        result = run(api.get_file("file-1"))

        assert isinstance(result, GetFileResponse)
        assert result.id == "file-1"
        assert result.snapshot == "snap-1"
        assert result.url == "http://example.com/index.html"
        assert result.protocol == "http"
        assert result.port == 80
        assert result.host == "example.com"
        assert result.path == "/index.html"

    def test_nested_request_and_response_info(self, api, backend):
        backend.respond(200, FILE_BODY)

        result = run(api.get_file("file-1"))

        assert result.request.sent_time == Timespec(1, 2)
        assert result.request.method == "GET"
        assert result.request.headers == {"Accept": ["*/*"]}
        assert result.request.parameters == {"q": ["1"]}
        assert result.response.received_time == Timespec(3, 4)
        assert result.response.code == 200
        assert result.response.headers == {"Content-Type": ["text/html"]}

    def test_request_method_and_url(self, api, backend):
        backend.respond(200, FILE_BODY)

        run(api.get_file("file-1"))

        assert backend.last["method"] == "GET"
        assert backend.last["url"] == f"{BASE}/files/file-1"

    def test_not_found(self, api, backend):
        backend.respond(404, {"message": "no such file"})

        with pytest.raises(NotFoundError) as exc:
            run(api.get_file("missing"))

        assert str(exc.value) == "no such file"

    def test_invalid_json_raises_bad_response_error(self, api, backend):
        backend.respond(200, raw="garbage")

        with pytest.raises(BadResponseError):
            run(api.get_file("file-1"))

    def test_body_missing_fields_raises_bad_response_error(self, api, backend):
        backend.respond(200, {"id": "file-1"})

        with pytest.raises(BadResponseError):
            run(api.get_file("file-1"))


#################
# get_file_data #
#################
class TestGetFileData:
    def test_success_returns_raw_response(self, api, backend):
        backend.response = httpx.Response(200, content=b"\x00\x01binary")

        result = run(api.get_file_data("file-1"))

        assert result is backend.response
        assert result.content == b"\x00\x01binary"

    def test_request_method_and_url(self, api, backend):
        backend.response = httpx.Response(200, content=b"data")

        run(api.get_file_data("file-1"))

        assert backend.last["method"] == "GET"
        assert backend.last["url"] == f"{BASE}/files/file-1/data"

    def test_not_found(self, api, backend):
        backend.respond(404, {"message": "no data"})

        with pytest.raises(NotFoundError) as exc:
            run(api.get_file_data("missing"))

        assert str(exc.value) == "no data"

    def test_server_error(self, api, backend):
        backend.respond(500, {"message": "boom"})

        with pytest.raises(InternalServerError) as exc:
            run(api.get_file_data("file-1"))

        assert str(exc.value) == "boom"

    def test_other_statuses_are_returned_not_raised(self, api, backend):
        # only 404 and 500 are translated into exceptions
        backend.response = httpx.Response(403, content=b"forbidden")

        result = run(api.get_file_data("file-1"))

        assert result.status_code == 403


###################
# query_snapshots #
###################
class TestQuerySnapshots:
    def test_success(self, api, backend):
        backend.respond(200, {"snapshot_ids": ["s1", "s2"]})

        result = run(api.query_snapshots("url", "http://example.com"))

        assert isinstance(result, SnapshotQueryResponse)
        assert list(result.snapshot_ids) == ["s1", "s2"]

    def test_request_with_field(self, api, backend):
        backend.respond(200, {"snapshot_ids": []})

        run(api.query_snapshots("url", "http://example.com"))

        assert backend.last["method"] == "QUERY"
        assert backend.last["url"] == f"{BASE}/search/snapshots"
        assert json.loads(backend.last["content"]) == {"url": "http://example.com"}

    @pytest.mark.parametrize("field", ["", None])
    def test_empty_field_sends_empty_object(self, api, backend, field):
        backend.respond(200, {"snapshot_ids": []})

        run(api.query_snapshots(field, "ignored"))

        assert json.loads(backend.last["content"]) == {}

    def test_bad_request(self, api, backend):
        backend.respond(400, {"message": "unknown field"})

        with pytest.raises(BadRequestError) as exc:
            run(api.query_snapshots("bogus", "x"))

        assert str(exc.value) == "unknown field"

    def test_invalid_json_raises_bad_response_error(self, api, backend):
        backend.respond(200, raw="nope")

        with pytest.raises(BadResponseError):
            run(api.query_snapshots("url", "x"))

    def test_wrong_shape_raises_bad_response_error(self, api, backend):
        backend.respond(200, {"unexpected": 1})

        with pytest.raises(BadResponseError):
            run(api.query_snapshots("url", "x"))


###############
# query_files #
###############
class TestQueryFiles:
    def test_success(self, api, backend):
        backend.respond(
            200,
            {
                "snapfilepairs": [
                    {"snapshot_id": "s1", "file_id": "f1"},
                    {"snapshot_id": "s2", "file_id": "f2"},
                ]
            },
        )

        result = run(api.query_files("host", "example.com"))

        assert isinstance(result, FileQueryResponse)
        pairs = [(p.snapshot_id, p.file_id) for p in result.snapfilepairs]
        assert pairs == [("s1", "f1"), ("s2", "f2")]

    def test_request_with_field(self, api, backend):
        backend.respond(200, {"snapfilepairs": []})

        run(api.query_files("host", "example.com"))

        assert backend.last["method"] == "QUERY"
        assert backend.last["url"] == f"{BASE}/search/files"
        assert json.loads(backend.last["content"]) == {"host": "example.com"}

    @pytest.mark.parametrize("field", ["", None])
    def test_empty_field_sends_empty_object(self, api, backend, field):
        backend.respond(200, {"snapfilepairs": []})

        run(api.query_files(field, "ignored"))

        assert json.loads(backend.last["content"]) == {}

    def test_bad_request(self, api, backend):
        backend.respond(400, {"message": "unknown field"})

        with pytest.raises(BadRequestError):
            run(api.query_files("bogus", "x"))

    def test_server_error(self, api, backend):
        backend.respond(500, {"message": "boom"})

        with pytest.raises(InternalServerError):
            run(api.query_files("host", "x"))

    def test_invalid_json_raises_bad_response_error(self, api, backend):
        backend.respond(200, raw="nope")

        with pytest.raises(BadResponseError):
            run(api.query_files("host", "x"))

    def test_wrong_shape_raises_bad_response_error(self, api, backend):
        backend.respond(200, {"unexpected": 1})

        with pytest.raises(BadResponseError):
            run(api.query_files("host", "x"))
            