"""
Webber Frontend Client API

This file contains code for requesting the backend from the frontend.
"""

from http import HTTPStatus
from typing import Any, overload, Iterable
from collections.abc import Callable
from functools import total_ordering
import json
import httpx
from .util.strictnamedtuple import StrictNamedTuple
from .util.convpath import convert_object
from copy import deepcopy
from enum import Enum

from PySide6.QtCore import QDateTime


def _to_json(obj: Any) -> str:
    """Encode obj to JSON, handling StrictNamedTuple objects."""

    def rec(cur: Any) -> Any:
        if isinstance(cur, StrictNamedTuple):
            return {name: cur[i] for i, name in enumerate(cur._fields)}
        elif isinstance(cur, (list, tuple)):
            return list(map(rec, cur))
        elif isinstance(cur, dict):
            return {name: rec(val) for name, val in cur.items()}
        else:
            return cur

    return json.dumps(rec(obj))


class ContentType(str, Enum):
    EMPTY = None
    JSON = "application/json"


################
# Global types #
################
@total_ordering
class Timespec(StrictNamedTuple):
    """Class representing an instant in time or an interval."""

    # seconds part
    sec: int

    # nanoseconds part (in range [0,999'999'999])
    nsec: int

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Timespec):
            return False
        return self.sec == other.sec and self.nsec == other.nsec

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Timespec):
            return False
        elif self.sec == other.sec:
            return self.nsec < other.nsec
        return self.sec < other.sec

    def to_qdatetime(self) -> QDateTime:
        """Convert this Timespec into a QDateTime.

        Note that QDateTime only has milisecond resolution, while Timespec has
        nanosecond resolution.

        Return: a QDateTime representing this Timespec
        """
        return QDateTime.fromMSecsSinceEpoch(
            self.sec * 1000 + self.nsec // 1000000
        )

    @staticmethod
    def from_qdatetime(dt: QDateTime) -> "Timespec":
        """Construct a Timespec from a QDateTime.

        Arguments:
        dt -- the QDateTime object to convert (not modified)

        Returns: the new Timespec
        """
        msec = dt.toMSecsSinceEpoch()
        return Timespec(msec // 1000, (msec % 1000) * 1000000)


# Error Types
class APIError(Exception):
    """Root of the API error hierarchy."""

    # The HTTP response code
    code: int | None

    # A human readable name for the error
    name: str

    def __init_subclass__(
        cls, /, code: int | None = None, name: str | None = None, **kwargs
    ):
        super().__init_subclass__(**kwargs)
        if code is not None:
            cls.code = code
        if name is not None:
            cls.name = name
        elif code is not None:
            cls.name = HTTPStatus(code).phrase

        real_repr = cls.__repr__

        def wrap_repr(self: BaseException) -> str:
            name = getattr(self, "name", None) or "??"
            code = getattr(self, "code", None)
            if code is None:
                return f"{name}: {real_repr(self)}"
            else:
                return f"{name} ({code}): {real_repr(self)}"

        cls.__repr__ = wrap_repr  # type: ignore[method-assign]

        if code is not None:
            real_init = cls.__init__

            @overload
            def wrap_init(self: BaseException, body: str): ...
            @overload
            def wrap_init(self: BaseException, code: int, body: str): ...
            def wrap_init(self: BaseException, *args, **kwargs):
                match args:
                    case () if "body" in kwargs:
                        real_init(self, json.loads(kwargs["body"]))
                    case (body,):
                        real_init(self, json.loads(body))
                    case (_, body):
                        real_init(self, json.loads(body))

            cls.__init__ = wrap_init  # type: ignore[method-assign, assignment]

    @overload
    def __new__(cls, code: int, body: str) -> "APIError":
        """Create an return a new `APIError` subclass based on code.

        Arguments:
        code -- the HTTP status code of the errored response
        body -- the body of the response, decoded to a string

        Returns: the new concrete subclass
        """
        ...

    @overload
    def __new__(cls, *args, **kwargs) -> "APIError": ...

    def __new__(cls, *args, **kwargs) -> "APIError":
        """Do the real work of creating the concrete `APIError` subclass."""
        if cls is APIError:
            try:
                for subcls in cls.__subclasses__():
                    if getattr(subcls, "code", None) == args[0]:
                        return Exception.__new__(subcls)
            except Exception:
                pass
            return UnknownAPIError(args[0], args[1])
        return Exception.__new__(cls)


class UnknownAPIError(APIError, name="Unknown Error"):
    """Represents an error that is out of spec."""

    body: str

    def __init__(self, code: int, body: str):
        self.code = code
        self.body = body

    def __str__(self) -> str:
        return self.body


class BadResponseError(APIError, name="Bad Response"):
    """Represents an API success response that is out of spec."""

    def __init__(self, body: str):
        self.code = None
        self.body = body

    def __str__(self) -> str:
        return self.body


class InternalServerError(APIError, code=500):
    """Represents an HTTP code 500."""

    def __init__(self, json_body: Any):
        self.message = json_body["message"]

    def __str__(self) -> str:
        return self.message


class BadRequestError(APIError, code=400):
    """Represents an HTTP code 400."""

    def __init__(self, json_body: Any):
        self.message = json_body["message"]

    def __str__(self) -> str:
        return self.message


###########################
# Endpoint specific types #
###########################


# /statistics
class Interval(StrictNamedTuple):
    """Represents a span of time.

    The start is inclusive, but the end is exclusive.
    """

    # the start of the interval (inclusive)
    start: Timespec | None

    # the end of the interval (exclusive)
    end: Timespec | None

    def __contains__(self, time: object) -> bool:
        if not isinstance(time, Timespec):
            raise TypeError(
                f"Cannot check if a {type(time)} falls in the interval"
            )
        if self.start is not None and self.end is not None:
            return self.start <= time < self.end
        elif self.start is not None:
            return self.start <= time
        elif self.end is not None:
            return time < self.end
        else:
            return True


class Statistics(StrictNamedTuple):
    """Represents database statistics over an interval."""

    # the interval of the statistics
    interval: Interval

    # the number of snapshots started over the interval
    snapshots: int

    # the number of files belonging to snapshots during this interval
    files: int

    # the sum of logical file sizes (in bytes) of files belonging to snapshots
    # over this interval
    size: int

    # the number of distinct URLs used to start snapshots over this interval
    urls: int

    # the number of distinct hosts represented in snapshots over this interval
    hosts: int


class StatisticsResponse(StrictNamedTuple):
    """Class representing a response from the `/statistics` endpoint."""

    statistics: list[Statistics]


class StatisticsLimitsResponse(StrictNamedTuple):
    """Class representing a response from the `/statistics/limits` endpoint."""

    first_snapshot: Timespec | None
    last_snapshot: Timespec | None


###########
# The API #
###########
class WebberAPI:
    def __init__(self, base_url: str):
        """Construct the API object.

        Arguments:
        base_url -- the base URL of the backend
        """
        self.base_url = base_url.removesuffix("/")
        self.client = httpx.AsyncClient()

    async def aclose(self):
        """Close the client associated with this instance."""
        await self.client.aclose()

    def _endpoint(self, endpoint: str) -> str:
        return self.base_url + endpoint

    async def _request(
        self,
        method: str,
        endpoint: str,
        content_type: ContentType,
        body: Any = None,
    ) -> httpx.Response:
        match content_type:
            case ContentType.EMPTY:
                return await self.client.request(
                    method, self._endpoint(endpoint)
                )
            case ContentType.JSON:
                json_str = _to_json(body)
                return await self.client.request(
                    method,
                    self._endpoint(endpoint),
                    headers={"Content-Type": content_type},
                    content=json_str.encode(),
                )

    def _body_json(self, resp: httpx.Response, expected_status: int) -> Any:
        if resp.status_code != expected_status:
            raise APIError(resp.status_code, resp.text)
        try:
            return resp.json()
        except Exception as e:
            raise BadResponseError(resp.text) from e

    async def statistics(
        self, intervals: list[Interval]
    ) -> StatisticsResponse:
        """Make a request to the `/statistics` endpoint.

        Arguments:
        intervals -- the interval over which to take the statistics

        Returns: the response
        """
        resp = await self._request(
            "QUERY",
            "/statistics",
            ContentType.JSON,
            {"intervals": intervals},
        )
        body = self._body_json(resp, 200)
        try:
            obj: StatisticsResponse = convert_object(
                [
                    ("-[].interval.start**", Timespec),
                    ("-[].interval.end**", Timespec),
                    ("[].interval**", Interval),
                    ("[]**", Statistics),
                    ("", StatisticsResponse),
                ],
                body["statistics"],
            )
            if len(intervals) != len(obj.statistics):
                raise Exception("Output length is != to input length")
            return obj
        except Exception as e:
            raise BadResponseError(resp.text) from e

    async def statistics_limits(self) -> StatisticsLimitsResponse:
        """Make a request to the `/statistics/limits` endpoint.

        Returns: the response
        """
        resp = await self._request(
            "GET",
            "/statistics/limits",
            ContentType.EMPTY,
        )
        body = self._body_json(resp, 200)
        try:
            obj = convert_object(
                [
                    ("-first_snapshot**", Timespec),
                    ("-last_snapshot**", Timespec),
                    ("**", StatisticsLimitsResponse),
                ],
                body,
            )
            # Only one time is None
            if sum(map(bool, obj)) == 1:
                raise Exception("Only one end of statistics limits is None")
            return obj
        except Exception as e:
            raise BadResponseError(resp.text) from e
