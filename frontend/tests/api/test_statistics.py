import pytest
import httpx
import respx  # type: ignore[import-not-found]
import json
from typing import Any
from frontend.src.api import (
    WebberAPI,
    Timespec,
    Interval,
    BadRequestError,
    BadResponseError,
    InternalServerError,
)


# Test Interval
class TestInterval:
    def test_contains_both_bounds(self):
        start = Timespec(10, 0)
        end = Timespec(20, 0)
        interval = Interval(start, end)
        assert Timespec(15, 0) in interval
        assert Timespec(10, 0) in interval  # inclusive
        assert Timespec(19, 0) in interval  # exclusive
        assert Timespec(20, 0) not in interval  # exclusive
        assert Timespec(5, 0) not in interval
        assert Timespec(25, 0) not in interval

    def test_contains_start_only(self):
        start = Timespec(10, 0)
        interval = Interval(start, None)
        assert Timespec(15, 0) in interval
        assert Timespec(5, 0) not in interval

    def test_contains_end_only(self):
        end = Timespec(20, 0)
        interval = Interval(None, end)
        assert Timespec(15, 0) in interval
        assert Timespec(25, 0) not in interval

    def test_contains_infinite(self):
        interval = Interval(None, None)
        assert Timespec(100, 0) in interval

    def test_contains_wrong_type(self):
        interval = Interval(None, None)
        with pytest.raises(TypeError):
            _ = 5 in interval


class TestStatistics:
    @pytest.fixture
    def api(self):
        return WebberAPI("https://example.com/api")

    @pytest.mark.asyncio
    @respx.mock
    async def test_statistics_success(self, api):
        # Mock the HTTP endpoint
        respx.route(method="QUERY", path="/api/statistics").mock(
            return_value=httpx.Response(
                200,
                json={
                    "statistics": [
                        {
                            "interval": {
                                "start": {"sec": 10, "nsec": 0},
                                "end": {"sec": 20, "nsec": 0},
                            },
                            "snapshots": 5,
                            "files": 100,
                            "size": 1024,
                            "urls": 3,
                            "hosts": 2,
                        }
                    ]
                },
            )
        )

        # Call the API
        intervals = [Interval(Timespec(10, 0), Timespec(20, 0))]
        result = await api.statistics(intervals)

        # Verify the result
        assert len(result.statistics) == 1
        stat = result.statistics[0]
        assert stat.interval.start == Timespec(10, 0)
        assert stat.interval.end == Timespec(20, 0)
        assert stat.snapshots == 5
        assert stat.files == 100

    @pytest.mark.asyncio
    @respx.mock
    async def test_statistics_null_intervals(self, api):
        respx.route(method="QUERY", path="/api/statistics").mock(
            return_value=httpx.Response(
                200,
                json={
                    "statistics": [
                        {
                            "interval": {"start": None, "end": None},
                            "snapshots": 0,
                            "files": 0,
                            "size": 0,
                            "urls": 0,
                            "hosts": 0,
                        }
                    ]
                },
            )
        )

        result = await api.statistics([])
        assert result.statistics[0].interval.start is None
        assert result.statistics[0].interval.end is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_statistics_error_500(self, api):
        respx.route(method="QUERY", path="/api/statistics").mock(
            return_value=httpx.Response(
                500, json={"message": "Internal error"}
            )
        )

        with pytest.raises(InternalServerError) as exc_info:
            await api.statistics([])
        print(repr(exc_info.value))
        assert "Internal error" in str(exc_info.value)

    @pytest.mark.asyncio
    @respx.mock
    async def test_statistics_error_400(self, api):
        respx.route(method="QUERY", path="/api/statistics").mock(
            return_value=httpx.Response(400, json={"message": "Bad request"})
        )

        with pytest.raises(BadRequestError):
            await api.statistics([])

    @pytest.mark.asyncio
    @respx.mock
    async def test_statistics_bad_json(self, api):
        respx.route(method="QUERY", path="/api/statistics").mock(
            return_value=httpx.Response(
                200, text="not json", headers={"Content-Type": "text/plain"}
            )
        )

        with pytest.raises(BadResponseError):
            await api.statistics([])

    @pytest.mark.asyncio
    @respx.mock
    async def test_statistics_malformed_response(self, api):
        # Server returns 200 but wrong structure
        respx.route(method="QUERY", path="/api/statistics").mock(
            return_value=httpx.Response(200, json={"unexpected": "data"})
        )

        with pytest.raises(BadResponseError):
            await api.statistics([])

    @pytest.mark.asyncio
    async def test_request_serialization(self):
        """Test that intervals are properly serialized in request body."""
        captured_request: Any = None

        def capture_request(request):
            nonlocal captured_request
            captured_request = request
            return httpx.Response(200, json={"statistics": []})

        with respx.mock:
            respx.route(method="QUERY").mock(side_effect=capture_request)

            api = WebberAPI("https://example.com")
            await api.statistics([Interval(None, None)])

            # Verify the request body contains serialized intervals
            body = json.loads(captured_request.content)
            assert "intervals" in body
            assert body["intervals"][0] == {"start": None, "end": None}
