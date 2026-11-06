import pytest
import respx  # type: ignore[import-not-found]
import httpx

from frontend.src.api import (
    WebberAPI,
    Timespec,
    InternalServerError,
    BadRequestError,
    BadResponseError,
)


# Test StatisticsLimits
class TestStatisticsLimits:
    @pytest.fixture
    def api(self):
        return WebberAPI("https://example.com/api")

    @pytest.mark.asyncio
    @respx.mock
    async def test_statistics_limits_success(self, api):
        respx.route(method="GET", path="/api/statistics/limits").mock(
            return_value=httpx.Response(
                200,
                json={
                    "first_snapshot": {"sec": 10, "nsec": 0},
                    "last_snapshot": {"sec": 20, "nsec": 0},
                },
            )
        )

        result = await api.statistics_limits()
        assert result.first_snapshot == Timespec(10, 0)
        assert result.last_snapshot == Timespec(20, 0)

    @pytest.mark.asyncio
    @respx.mock
    async def test_statistics_limits_null_values(self, api):
        respx.route(method="GET", path="/api/statistics/limits").mock(
            return_value=httpx.Response(
                200,
                json={
                    "first_snapshot": None,
                    "last_snapshot": {"sec": 20, "nsec": 0},
                },
            )
        )

        with pytest.raises(BadResponseError):
            await api.statistics_limits()

    @pytest.mark.asyncio
    @respx.mock
    async def test_statistics_limits_one_null_value(self, api):
        respx.route(method="GET", path="/api/statistics/limits").mock(
            return_value=httpx.Response(
                200,
                json={
                    "first_snapshot": None,
                    "last_snapshot": None,
                },
            )
        )

        result = await api.statistics_limits()
        assert result.first_snapshot is None
        assert result.last_snapshot is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_statistics_limits_error_500(self, api):
        respx.route(method="GET", path="/api/statistics/limits").mock(
            return_value=httpx.Response(
                500, json={"message": "Internal error"}
            )
        )

        with pytest.raises(InternalServerError):
            await api.statistics_limits()

    @pytest.mark.asyncio
    @respx.mock
    async def test_statistics_limits_error_400(self, api):
        respx.route(method="GET", path="/api/statistics/limits").mock(
            return_value=httpx.Response(400, json={"message": "Bad request"})
        )

        with pytest.raises(BadRequestError):
            await api.statistics_limits()

    @pytest.mark.asyncio
    @respx.mock
    async def test_statistics_limits_bad_json(self, api):
        respx.route(method="GET", path="/api/statistics/limits").mock(
            return_value=httpx.Response(
                200, text="not json", headers={"Content-Type": "text/plain"}
            )
        )

        with pytest.raises(BadResponseError):
            await api.statistics_limits()

    @pytest.mark.asyncio
    @respx.mock
    async def test_statistics_limits_malformed_response(self, api):
        respx.route(method="GET", path="/api/statistics/limits").mock(
            return_value=httpx.Response(200, json={"unexpected": "data"})
        )

        with pytest.raises(BadResponseError):
            await api.statistics_limits()
