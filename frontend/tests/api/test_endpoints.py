import pytest
import httpx
import respx  # type: ignore[import-not-found]
import json
from typing import Any
from frontend.src.api import (
    WebberAPI,
    Timespec,
    BadRequestError,
    BadResponseError,
    InternalServerError,
    GetSnapshotResponse,
)


class TestCreateSnapshot:
    @pytest.fixture
    def api(self):
        return WebberAPI("https://example.com/api")

    @pytest.mark.asyncio
    @respx.mock
    async def test_create_snapshot_success(self, api):
        respx.route(method="POST", path="/api/snapshots/create").mock(
            return_value=httpx.Response(
                201,
                json={"id": "snapshot-123"},
            )
        )

        result = await api.create_snapshot(
            "https://example.com/page", "GET", headers={"User-Agent": ["test"]}
        )
        assert result == "snapshot-123"

    @pytest.mark.asyncio
    @respx.mock
    async def test_create_snapshot_success_minimal(self, api):
        respx.route(method="POST", path="/api/snapshots/create").mock(
            return_value=httpx.Response(201, json={"id": "abc"})
        )

        result = await api.create_snapshot("https://example.com", "GET")
        assert result == "abc"

    @pytest.mark.asyncio
    @respx.mock
    async def test_create_snapshot_error_500(self, api):
        respx.route(method="POST", path="/api/snapshots/create").mock(
            return_value=httpx.Response(
                500, json={"message": "Internal error"}
            )
        )

        with pytest.raises(InternalServerError):
            await api.create_snapshot("https://example.com", "GET")

    @pytest.mark.asyncio
    @respx.mock
    async def test_create_snapshot_error_400(self, api):
        respx.route(method="POST", path="/api/snapshots/create").mock(
            return_value=httpx.Response(400, json={"message": "Bad request"})
        )

        with pytest.raises(BadRequestError):
            await api.create_snapshot("https://example.com", "GET")

    @pytest.mark.asyncio
    @respx.mock
    async def test_create_snapshot_bad_json(self, api):
        respx.route(method="POST", path="/api/snapshots/create").mock(
            return_value=httpx.Response(
                201,
                text="not json",
                headers={"Content-Type": "text/plain"},
            )
        )

        with pytest.raises(BadResponseError):
            await api.create_snapshot("https://example.com", "GET")

    @pytest.mark.asyncio
    @respx.mock
    async def test_create_snapshot_malformed_response(self, api):
        # Response missing "id" field
        respx.route(method="POST", path="/api/snapshots/create").mock(
            return_value=httpx.Response(201, json={"unexpected": "data"})
        )

        with pytest.raises(BadResponseError):
            await api.create_snapshot("https://example.com", "GET")

    @pytest.mark.asyncio
    @respx.mock
    async def test_create_snapshot_id_not_string(self, api):
        # Response has id but not a string
        respx.route(method="POST", path="/api/snapshots/create").mock(
            return_value=httpx.Response(201, json={"id": 123})
        )

        with pytest.raises(BadResponseError):
            await api.create_snapshot("https://example.com", "GET")

    @pytest.mark.asyncio
    async def test_request_serialization(self):
        """Test that the request body is properly serialized."""
        captured_request: Any = None

        def capture_request(request):
            nonlocal captured_request
            captured_request = request
            return httpx.Response(201, json={"id": "snapshot-123"})

        with respx.mock:
            respx.route(method="POST", path="/api/snapshots/create").mock(
                side_effect=capture_request
            )

            api = WebberAPI("https://example.com/api")
            await api.create_snapshot(
                "https://example.com/page",
                "POST",
                headers={"Content-Type": ["application/json"]},
            )

            # Verify the request body
            body = json.loads(captured_request.content)
            assert body["url"] == "https://example.com/page"
            assert body["request_options"]["method"] == "POST"
            assert body["request_options"]["headers"] == {
                "Content-Type": ["application/json"]
            }


class TestDeleteSnapshot:
    @pytest.fixture
    def api(self):
        return WebberAPI("https://example.com/api")

    @pytest.mark.asyncio
    @respx.mock
    async def test_delete_snapshot_success(self, api):
        respx.route(method="DELETE", path="/api/snapshots/snapshot-123").mock(
            return_value=httpx.Response(202)
        )

        await api.delete_snapshot("snapshot-123")  # Should not raise

    @pytest.mark.asyncio
    @respx.mock
    async def test_delete_snapshot_error_500(self, api):
        respx.route(method="DELETE", path="/api/snapshots/snapshot-123").mock(
            return_value=httpx.Response(
                500, json={"message": "Internal error"}
            )
        )

        with pytest.raises(InternalServerError):
            await api.delete_snapshot("snapshot-123")

    @pytest.mark.asyncio
    @respx.mock
    async def test_delete_snapshot_error_400(self, api):
        respx.route(method="DELETE", path="/api/snapshots/snapshot-123").mock(
            return_value=httpx.Response(400, json={"message": "Bad request"})
        )

        with pytest.raises(BadRequestError):
            await api.delete_snapshot("snapshot-123")

    @pytest.mark.asyncio
    @respx.mock
    async def test_delete_snapshot_wrong_status(self, api):
        # Should expect 202, but gets 200
        respx.route(method="DELETE", path="/api/snapshots/snapshot-123").mock(
            return_value=httpx.Response(200)
        )

        with pytest.raises(Exception):
            await api.delete_snapshot("snapshot-123")

    @pytest.mark.asyncio
    async def test_id_url_encoding(self):
        """Test that special characters in ID are URL-encoded."""
        captured_url: Any = None

        def capture_request(request):
            nonlocal captured_url
            captured_url = str(request.url)
            return httpx.Response(202)

        with respx.mock:
            respx.route(method="DELETE").mock(side_effect=capture_request)

            api = WebberAPI("https://example.com/api")
            await api.delete_snapshot("snapshot/with/slashes")

            assert "snapshot%2Fwith%2Fslashes" in captured_url


class TestGetSnapshotInfo:
    @pytest.fixture
    def api(self):
        return WebberAPI("https://example.com/api")

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_snapshot_info_success(self, api):
        respx.route(method="GET", path="/api/snapshots/snapshot-123").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "snapshot-123",
                    "url": "https://example.com/page",
                    "start_time": {"sec": 10, "nsec": 0},
                    "end_time": {"sec": 11, "nsec": 0},
                    "files": ["file-1", "file-2"],
                },
            )
        )

        result = await api.get_snapshot_info("snapshot-123")
        assert result.id == "snapshot-123"
        assert result.url == "https://example.com/page"
        assert result.start_time == Timespec(10, 0)
        assert result.end_time == Timespec(11, 0)
        assert result.files == ["file-1", "file-2"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_snapshot_info_error_500(self, api):
        respx.route(method="GET", path="/api/snapshots/snapshot-123").mock(
            return_value=httpx.Response(
                500, json={"message": "Internal error"}
            )
        )

        with pytest.raises(InternalServerError):
            await api.get_snapshot_info("snapshot-123")

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_snapshot_info_error_400(self, api):
        respx.route(method="GET", path="/api/snapshots/snapshot-123").mock(
            return_value=httpx.Response(400, json={"message": "Bad request"})
        )

        with pytest.raises(BadRequestError):
            await api.get_snapshot_info("snapshot-123")

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_snapshot_info_bad_json(self, api):
        respx.route(method="GET", path="/api/snapshots/snapshot-123").mock(
            return_value=httpx.Response(
                200, text="not json", headers={"Content-Type": "text/plain"}
            )
        )

        with pytest.raises(BadResponseError):
            await api.get_snapshot_info("snapshot-123")

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_snapshot_info_malformed_response(self, api):
        # Missing required fields
        respx.route(method="GET", path="/api/snapshots/snapshot-123").mock(
            return_value=httpx.Response(200, json={"unexpected": "data"})
        )

        with pytest.raises(BadResponseError):
            await api.get_snapshot_info("snapshot-123")


class TestGetFileInfo:
    @pytest.fixture
    def api(self):
        return WebberAPI("https://example.com/api")

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_file_info_success(self, api):
        respx.route(method="GET", path="/api/files/file-123").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "file-123",
                    "snapshot": "snapshot-123",
                    "url": "https://example.com/page/file.html",
                    "protocol": "https",
                    "port": 443,
                    "host": "example.com",
                    "path": "/page/file.html",
                    "request": {
                        "sent_time": {"sec": 10, "nsec": 0},
                        "method": "GET",
                        "headers": {"User-Agent": ["test"]},
                        "parameters": {},
                    },
                    "response": {
                        "received_time": {"sec": 10, "nsec": 500000000},
                        "code": 200,
                        "headers": {"Content-Type": ["text/html"]},
                    },
                },
            )
        )

        result = await api.get_file_info("file-123")
        assert result.id == "file-123"
        assert result.snapshot == "snapshot-123"
        assert result.url == "https://example.com/page/file.html"
        assert result.protocol == "https"
        assert result.port == 443
        assert result.host == "example.com"
        assert result.path == "/page/file.html"
        assert result.request.sent_time == Timespec(10, 0)
        assert result.request.method == "GET"
        assert result.response.received_time == Timespec(10, 500000000)
        assert result.response.code == 200

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_file_info_error_500(self, api):
        respx.route(method="GET", path="/api/files/file-123").mock(
            return_value=httpx.Response(
                500, json={"message": "Internal error"}
            )
        )

        with pytest.raises(InternalServerError):
            await api.get_file_info("file-123")

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_file_info_error_400(self, api):
        respx.route(method="GET", path="/api/files/file-123").mock(
            return_value=httpx.Response(400, json={"message": "Bad request"})
        )

        with pytest.raises(BadRequestError):
            await api.get_file_info("file-123")

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_file_info_bad_json(self, api):
        respx.route(method="GET", path="/api/files/file-123").mock(
            return_value=httpx.Response(
                200, text="not json", headers={"Content-Type": "text/plain"}
            )
        )

        with pytest.raises(BadResponseError):
            await api.get_file_info("file-123")

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_file_info_malformed_response(self, api):
        # Missing required fields
        respx.route(method="GET", path="/api/files/file-123").mock(
            return_value=httpx.Response(200, json={"unexpected": "data"})
        )

        with pytest.raises(BadResponseError):
            await api.get_file_info("file-123")


class TestGetFileData:
    @pytest.fixture
    def api(self):
        return WebberAPI("https://example.com/api")

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_file_data_success(self, api):
        respx.route(method="GET", path="/api/files/file-123/data").mock(
            return_value=httpx.Response(
                200,
                content=b"<html><body>test</body></html>",
                headers={"Content-Type": "text/html"},
            )
        )

        result = await api.get_file_data("file-123")
        assert result.status_code == 200
        assert result.content == b"<html><body>test</body></html>"

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_file_data_error_500(self, api):
        respx.route(method="GET", path="/api/files/file-123/data").mock(
            return_value=httpx.Response(
                500, json={"message": "Internal error"}
            )
        )

        result = await api.get_file_data("file-123")
        assert result.status_code == 500

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_file_data_error_400(self, api):
        respx.route(method="GET", path="/api/files/file-123/data").mock(
            return_value=httpx.Response(400, json={"message": "Bad request"})
        )

        result = await api.get_file_data("file-123")
        assert result.status_code == 400


class TestSearchSnapshots:
    @pytest.fixture
    def api(self):
        return WebberAPI("https://example.com/api")

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_snapshots_success(self, api):
        respx.route(method="QUERY", path="/api/search/snapshots").mock(
            return_value=httpx.Response(
                200, json=["snap-1", "snap-2", "snap-3"]
            )
        )

        result = await api.search_snapshots()
        assert result == ["snap-1", "snap-2", "snap-3"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_snapshots_with_filters(self, api):
        respx.route(method="QUERY", path="/api/search/snapshots").mock(
            return_value=httpx.Response(200, json=["snap-1"])
        )

        result = await api.search_snapshots(
            start_time=Timespec(10, 0),
            end_time=Timespec(20, 0),
            url="example.*",
        )
        assert result == ["snap-1"]

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_snapshots_empty_result(self, api):
        respx.route(method="QUERY", path="/api/search/snapshots").mock(
            return_value=httpx.Response(200, json=[])
        )

        result = await api.search_snapshots()
        assert result == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_snapshots_error_500(self, api):
        respx.route(method="QUERY", path="/api/search/snapshots").mock(
            return_value=httpx.Response(
                500, json={"message": "Internal error"}
            )
        )

        with pytest.raises(InternalServerError):
            await api.search_snapshots()

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_snapshots_error_400(self, api):
        respx.route(method="QUERY", path="/api/search/snapshots").mock(
            return_value=httpx.Response(400, json={"message": "Bad request"})
        )

        with pytest.raises(BadRequestError):
            await api.search_snapshots()

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_snapshots_bad_json(self, api):
        respx.route(method="QUERY", path="/api/search/snapshots").mock(
            return_value=httpx.Response(
                200, text="not json", headers={"Content-Type": "text/plain"}
            )
        )

        with pytest.raises(BadResponseError):
            await api.search_snapshots()

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_snapshots_not_a_list(self, api):
        respx.route(method="QUERY", path="/api/search/snapshots").mock(
            return_value=httpx.Response(200, json={"unexpected": "data"})
        )

        with pytest.raises(BadResponseError):
            await api.search_snapshots()

    @pytest.mark.asyncio
    async def test_request_serialization(self):
        """Test that filters are properly serialized in request body."""
        captured_request: Any = None

        def capture_request(request):
            nonlocal captured_request
            captured_request = request
            return httpx.Response(200, json=[])

        with respx.mock:
            respx.route(method="QUERY", path="/api/search/snapshots").mock(
                side_effect=capture_request
            )

            api = WebberAPI("https://example.com/api")
            await api.search_snapshots(
                start_time=Timespec(10, 0),
                end_time=Timespec(20, 0),
                url="example.*",
            )

            body = json.loads(captured_request.content)
            assert body["start_time"] == {"sec": 10, "nsec": 0}
            assert body["end_time"] == {"sec": 20, "nsec": 0}
            assert body["url"] == "example.*"
            # None values should be omitted
            assert "snapshot_id" not in body


class TestSearchFiles:
    @pytest.fixture
    def api(self):
        return WebberAPI("https://example.com/api")

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_files_success(self, api):
        respx.route(method="QUERY", path="/api/search/files").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"snapshot_id": "snap-1", "file_id": "file-1"},
                    {"snapshot_id": "snap-1", "file_id": "file-2"},
                ],
            )
        )

        result = await api.search_files()
        assert len(result) == 2
        assert result[0].snapshot_id == "snap-1"
        assert result[0].file_id == "file-1"

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_files_with_filters(self, api):
        respx.route(method="QUERY", path="/api/search/files").mock(
            return_value=httpx.Response(
                200, json=[{"snapshot_id": "snap-1", "file_id": "file-1"}]
            )
        )

        result = await api.search_files(
            snapshot_id="snap-1",
            start_time=Timespec(10, 0),
            end_time=Timespec(20, 0),
            url=".*html",
            host="example.com",
            protocol="https",
            port=443,
            path="/*.css",
            status_codes=[200, 304],
        )
        assert len(result) == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_files_empty_result(self, api):
        respx.route(method="QUERY", path="/api/search/files").mock(
            return_value=httpx.Response(200, json=[])
        )

        result = await api.search_files()
        assert result == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_files_error_500(self, api):
        respx.route(method="QUERY", path="/api/search/files").mock(
            return_value=httpx.Response(
                500, json={"message": "Internal error"}
            )
        )

        with pytest.raises(InternalServerError):
            await api.search_files()

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_files_error_400(self, api):
        respx.route(method="QUERY", path="/api/search/files").mock(
            return_value=httpx.Response(400, json={"message": "Bad request"})
        )

        with pytest.raises(BadRequestError):
            await api.search_files()

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_files_bad_json(self, api):
        respx.route(method="QUERY", path="/api/search/files").mock(
            return_value=httpx.Response(
                200, text="not json", headers={"Content-Type": "text/plain"}
            )
        )

        with pytest.raises(BadResponseError):
            await api.search_files()

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_files_not_a_list(self, api):
        respx.route(method="QUERY", path="/api/search/files").mock(
            return_value=httpx.Response(200, json={"unexpected": "data"})
        )

        with pytest.raises(BadResponseError):
            await api.search_files()

    @pytest.mark.asyncio
    async def test_request_serialization(self):
        """Test that filters are properly serialized in request body."""
        captured_request: Any = None

        def capture_request(request):
            nonlocal captured_request
            captured_request = request
            return httpx.Response(200, json=[])

        with respx.mock:
            respx.route(method="QUERY", path="/api/search/files").mock(
                side_effect=capture_request
            )

            api = WebberAPI("https://example.com/api")
            await api.search_files(
                snapshot_id="snap-1",
                start_time=Timespec(10, 0),
                url=".*html",
                port=443,
                status_codes=[200],
            )

            body = json.loads(captured_request.content)
            assert body["snapshot_id"] == "snap-1"
            assert body["start_time"] == {"sec": 10, "nsec": 0}
            assert body["url"] == ".*html"
            assert body["port"] == 443
            assert body["status_codes"] == [200]
            # None values should be omitted
            assert "end_time" not in body
            assert "host" not in body
            assert "protocol" not in body
            assert "path" not in body
