# tests/test_api.py
import pytest
import json
from PySide6.QtCore import QDateTime
from frontend.src.api import (
    WebberAPI,
    Timespec,
    Interval,
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


# Test Timespec.to_qdatetime conversion
class TestTimespecToQDateTime:
    def test_to_qdatetime_seconds_only(self):
        t = Timespec(10, 0)
        qdt = t.to_qdatetime()
        assert qdt.toMSecsSinceEpoch() == 10000

    def test_to_qdatetime_with_nanoseconds(self):
        # 10 seconds + 500000000 ns (0.5s) = 10500 ms
        t = Timespec(10, 500000000)
        qdt = t.to_qdatetime()
        assert qdt.toMSecsSinceEpoch() == 10500

    def test_to_qdatetime_zero(self):
        t = Timespec(0, 0)
        qdt = t.to_qdatetime()
        assert qdt.toMSecsSinceEpoch() == 0

    def test_to_qdatetime_sub_second_only(self):
        # 999999999 ns = 999.999999 ms -> truncates to 999 ms
        t = Timespec(0, 999999999)
        qdt = t.to_qdatetime()
        assert qdt.toMSecsSinceEpoch() == 999

    def test_to_qdatetime_truncation(self):
        # 500000 ns = 0.5 ms -> truncates to 0
        t = Timespec(0, 500000)
        qdt = t.to_qdatetime()
        assert qdt.toMSecsSinceEpoch() == 0

    def test_to_qdatetime_returns_qdatetime(self):
        t = Timespec(1, 500)
        result = t.to_qdatetime()
        assert isinstance(result, QDateTime)
        assert not result.isNull()


# Test Timespec.from_qdatetime conversion
class TestTimespecFromQDateTime:
    def test_from_qdatetime_basic(self):
        # 10 seconds and 500 milliseconds
        dt = QDateTime.fromMSecsSinceEpoch(10500)
        ts = Timespec.from_qdatetime(dt)
        assert ts.sec == 10
        assert ts.nsec == 500000000  # 500 ms converted to nanoseconds

    def test_from_qdatetime_zero(self):
        dt = QDateTime.fromMSecsSinceEpoch(0)
        ts = Timespec.from_qdatetime(dt)
        assert ts.sec == 0
        assert ts.nsec == 0

    def test_from_qdatetime_sub_second_only(self):
        # 999 milliseconds = 0 seconds + 999000000 nanoseconds
        dt = QDateTime.fromMSecsSinceEpoch(999)
        ts = Timespec.from_qdatetime(dt)
        assert ts.sec == 0
        assert ts.nsec == 999000000

    def test_from_qdatetime_negative(self):
        # Before epoch: -1500 ms
        # Python floor division: -1500 // 1000 = -2, remainder = 500
        # Result: -2 sec + 500 ms = -1.5 sec
        dt = QDateTime.fromMSecsSinceEpoch(-1500)
        ts = Timespec.from_qdatetime(dt)
        assert ts.sec == -2
        assert ts.nsec == 500000000

    def test_from_qdatetime_returns_timespec(self):
        dt = QDateTime.fromMSecsSinceEpoch(12345)
        ts = Timespec.from_qdatetime(dt)
        assert isinstance(ts, Timespec)

    def test_from_qdatetime_roundtrip(self):
        """Verify that to_qdatetime/from_qdatetime preserve millisecond precision."""
        # Create Timespec with exact millisecond precision (500,000,000 ns = 500 ms)
        original = Timespec(10, 500000000)
        qdt = original.to_qdatetime()
        recovered = Timespec.from_qdatetime(qdt)
        assert recovered == original
        assert recovered.sec == 10
        assert recovered.nsec == 500000000

    def test_from_qdatetime_millisecond_precision(self):
        """Nanoseconds should be multiples of 1,000,000 (1 millisecond)."""
        dt = QDateTime.fromMSecsSinceEpoch(12345)
        ts = Timespec.from_qdatetime(dt)
        assert ts.sec == 12
        # nsec should be 345 ms expressed as nanoseconds
        assert ts.nsec == 345000000
        assert ts.nsec % 1000000 == 0  # Multiple of 1 millisecond


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
    def test_endpoint_url_construction(self):
        api = WebberAPI("https://example.com/api/")
        assert api._endpoint("/test") == "https://example.com/api/test"
