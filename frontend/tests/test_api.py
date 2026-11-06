# tests/test_api.py
from typing import Any
import pytest
import pytest_asyncio
import httpx
import respx
import json
from src.api import (
    WebberAPI,
    Timespec,
    Interval,
    Statistics,
    StatisticsResponse,
    APIError,
    UnknownAPIError,
    BadResponseError,
    InternalServerError,
    BadRequestError,
    _to_json,
)


# Test Timespec
class TestTimespec:
    def test_equality(self):
        t1 = Timespec(10, 500000000)
        t2 = Timespec(10, 500000000)
        t3 = Timespec(10, 500000001)
        assert t1 == t2
        assert t1 != t3

    def test_ordering(self):
        t1 = Timespec(10, 0)
        t2 = Timespec(10, 1)
        t3 = Timespec(11, 0)
        assert t1 < t2 < t3
        assert t3 > t2 > t1

    def test_immutable(self):
        t = Timespec(10, 500)
        with pytest.raises(AttributeError):
            t.sec = 20

    def test_tuple_access(self):
        t = Timespec(10, 500)
        assert t[0] == 10
        assert t[1] == 500
        assert t.sec == 10
        assert t.nsec == 500


# Test Interval
class TestInterval:
    def test_contains_both_bounds(self):
        start = Timespec(10, 0)
        end = Timespec(20, 0)
        interval = Interval(start, end)
        assert Timespec(15, 0) in interval
        assert Timespec(10, 0) in interval  # inclusive
        assert Timespec(20, 0) in interval  # inclusive
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


# Test APIError hierarchy
class TestAPIError:
    def test_error_creation_by_code(self):
        err = APIError(500, '{"message": "test"}')
        assert isinstance(err, InternalServerError)
        assert err.code == 500
        assert err.message == "test"

    def test_error_creation_400(self):
        err = APIError(400, '{"message": "bad"}')
        assert isinstance(err, BadRequestError)

    def test_error_creation_unknown(self):
        err = APIError(418, "teapot")
        assert isinstance(err, UnknownAPIError)
        assert err.code == 418

    def test_error_repr(self):
        err = InternalServerError('{"message": "oops"}')
        assert "oops" in str(err)


# Test JSON Encoder
class TestToJson:
    def test_encodes_namedtuple(self):
        t = Timespec(10, 500)
        encoded = _to_json(t)
        decoded = json.loads(encoded)
        assert decoded == {"sec": 10, "nsec": 500}

    def test_encodes_nested(self):
        data = {"times": [Timespec(1, 2), Timespec(3, 4)]}
        encoded = _to_json(data)
        decoded = json.loads(encoded)
        assert decoded["times"][0] == {"sec": 1, "nsec": 2}


# Test WebberAPI
class TestWebberAPI:
    @pytest.fixture
    def api(self):
        return WebberAPI("https://example.com/api")

    def test_endpoint_url_construction(self):
        api = WebberAPI("https://example.com/api/")
        assert api._endpoint("/test") == "https://example.com/api/test"

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


# Test StrictNamedTuple immutability via the types
class TestTypes:
    def test_statistics_immutable(self):
        stat = Statistics(
            interval=Interval(None, None),
            snapshots=1,
            files=2,
            size=3,
            urls=4,
            hosts=5,
        )
        with pytest.raises(AttributeError):
            stat.snapshots = 10

    def test_statistics_response_immutable(self):
        resp = StatisticsResponse(statistics=[])
        with pytest.raises(AttributeError):
            resp.statistics = [1, 2, 3]  # type: ignore[list-item]
