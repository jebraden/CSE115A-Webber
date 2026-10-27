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
    def test_endpoint_url_construction(self):
        api = WebberAPI("https://example.com/api/")
        assert api._endpoint("/test") == "https://example.com/api/test"
