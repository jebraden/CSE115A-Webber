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
import re


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

class NotFoundError(APIError, code=404):
    """Represents an HTTP code 404."""  

    def __init__(self, json_body: Any):
        self.message = json_body["message"]

    def __str__(self) -> str:
        return self.message


###########################
# Endpoint specific types #
###########################

# /snapshots/create
class CreateSnapshotResponse(StrictNamedTuple):
    """The response body of a snapshot creation request."""

    # the unique id representing the created snapshot
    id: str

# /snapshots/{SNAPSHOT_ID}
class GetSnapshotResponse(StrictNamedTuple):
    """The response body of a snapshot request"""

    # echo back SNAPSHOT_ID
    id: str

    # URL that triggered the snapshot
    url: str

    # time when the snapshot creation was started
    start_time: Timespec | None

    # time when the snapshot creation was finished
    end_time: Timespec | None

    # id files in this snapshot (see API.ORG for details)
    files: list[str]


# /files/{FILE_ID}
class ResponseInfo(StrictNamedTuple):
    """An object for storing information about the response"""

    # time when the response was received
    received_time: Timespec | None

    # code the server responded with when serving the file
    code: int

    # response headers
    headers: dict[str, list[str]]


class RequestInfo(StrictNamedTuple):
    """An object for storing information about the request"""

    # time when the file request was made
    sent_time: Timespec | None

    # HTTP request method
    method: str

    # HTTP request headers
    headers: dict[str, list[str]]

    # request parameters (from the URL)
    parameters: dict[str, list[str]]


class GetFileResponse(StrictNamedTuple):
    """A response from the /files/{FILE_ID} endpoint"""

    # echo the file id
    id: str

    # snapshot to which the file belongs
    snapshot: str

    # url to request the file
    url: str

    # protocol used to request the file
    protocol: str

    # port used to request the file
    port: int

    # (remote) host of the file
    host: str

    # relative path to file on (remote) host
    path: str

    # information about the request
    request: RequestInfo

    # information about the response
    response: ResponseInfo


# /search
class SnapshotQueryResponse(StrictNamedTuple):
    """A response from the /search/snapshots endpoint"""

    # a list of snapshot ids that matched the search
    snapshot_ids: list[str]

class SnapshotFilePair(StrictNamedTuple):
    """Holds a snapshot id and its corresponding file id"""

    # a snapshot id that matched the search
    snapshot_id: str

    # the snapshot id's associated file id
    file_id: str

class FileQueryResponse(StrictNamedTuple):
    """A response from the /search/files endpoint"""

    # a list of snapshot id/file id pairs
    snapfilepairs: list[SnapshotFilePair]


# /statistics
class Interval(StrictNamedTuple):
    """Represents a span of time.

    The start and end are inclusive.
    """

    # the start of the interval (inclusive)
    start: Timespec | None

    # the end of the interval (inclusive)
    end: Timespec | None

    def __contains__(self, time: object) -> bool:
        if not isinstance(time, Timespec):
            raise TypeError(
                f"Cannot check if a {type(time)} falls in the interval"
            )
        if self.start is not None and self.end is not None:
            return self.start <= time <= self.end
        elif self.start is not None:
            return self.start <= time
        elif self.end is not None:
            return time <= self.end
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

    def _endpoint(self, endpoint: str) -> str:
        return self.base_url + endpoint

    async def _request(
        self, client: httpx.AsyncClient, method: str, endpoint: str, body: Any
    ) -> httpx.Response:
        json_str = _to_json(body)
        return await client.request(
            method, self._endpoint(endpoint), content=json_str.encode()
        )

    def _body_json(self, resp: httpx.Response, expected_status: int) -> Any:
        if resp.status_code != expected_status:
            raise APIError(resp.status_code, resp.text)
        try:
            return resp.json()
        except Exception as e:
            raise BadResponseError(resp.text) from e

    async def create_snapshot(
        self, request_body: str
    ) -> CreateSnapshotResponse:
        """Make a POST request to the /snapshots/create endpoint

        Arguments:
        request_body -- the body of the snapshot creation request 
        """
        async with httpx.AsyncClient() as client:
            resp = await self._request(
                client, "POST", "/snapshots/create", request_body
            )

            body = self._body_json(resp, 201)

            try:
                return CreateSnapshotResponse(id=body["id"])
            except (TypeError, KeyError) as e:
                raise BadResponseError(resp.text) from e

    async def delete_snapshot(
            self, snapshot_id: str
    ) -> bool:
        """Make a DELETE request to the /snapshots/{SNAPSHOT_ID} endpoint

        Arguments:
        snapshot_id -- the id of the snapshot to delete
        """
        async with httpx.AsyncClient() as client:
            resp = await self._request(
                client, "DELETE", "/snapshots/" + snapshot_id, {}
            )

            if resp.status_code == 202:
                return True
            else:
                return False      

    async def get_snapshot(
            self, snapshot_id: str
    ) -> GetSnapshotResponse:
        """Make a GET request to the /snapshots/{SNAPSHOT_ID} endpoint

        Arguments:
        snapshot_id -- the id of the snapshot to request
        """
        async with httpx.AsyncClient() as client:
            resp = await self._request(
                client, "GET", "/snapshots/" + snapshot_id, {}
            )
            body = self._body_json(resp, 200)
            try:
                return convert_object(
                    [
                        ("-start_time**", Timespec),
                        ("-end_time**", Timespec),
                        ("**", GetSnapshotResponse)
                    ],
                    body
                )
            except Exception as e:
                raise BadResponseError(resp.text) from e


                
    async def get_file(
        self, file_id: str
    ) -> GetFileResponse:
        """Make a GET request to the /files/{FILE_ID} endpoint

        Arguments:
        file_id -- the id of the file to request
        """
        async with httpx.AsyncClient() as client:
            resp = await self._request(
                client, "GET", "/files/" + file_id, {}
            )
            body = self._body_json(resp, 200)
            try:
                return convert_object(
                    [
                        ("-request.sent_time**", Timespec),
                        ("request**", RequestInfo),
                        ("-response.received_time**", Timespec),
                        ("response**", ResponseInfo),
                        ("**", GetFileResponse)
                    ],
                    body
                )
            except Exception as e:
                raise BadResponseError(resp.text) from e

    async def get_file_data(
        self, file_id: str
    ) -> httpx.Response:
        """Make a GET request to the /files/{FILE_ID}/data endpoint

        Arguments:
        file_id -- the id of the file data to request
        """
        async with httpx.AsyncClient() as client:
            resp = await self._request(
                client, "GET", "/files/" + file_id + "/data", {}
            )

            if resp.status_code == 404:
                raise NotFoundError(resp.text)
            elif resp.status_code == 500:
                raise InternalServerError(resp.text)
            return resp

            
    async def query_snapshots(
        self, field: str, key: str
    ) -> SnapshotQueryResponse:
        """Make a QUERY request to the /search/snapshots endpoint

        Arguments:
        field -- the field to query (optional)
                    (valid fields: start_time, end_time, url)
        key -- the search key corresponding to the field (optional)
        """
        request_body = {field: key} if field else {}
        async with httpx.AsyncClient() as client:
            resp = await self._request(
                client, "QUERY", "/search/snapshots", request_body
            )
            body = self._body_json(resp, 200)
            try:
                return convert_object(
                    [
                        ("**", SnapshotQueryResponse)
                    ],
                    body
                )
            except Exception as e:
                raise BadResponseError(resp.text) from e


    async def query_files(
        self, field: str, key: str
    ) -> FileQueryResponse:
        """Make a QUERY request to the /search/files endpoint

        Arguments:
        field -- the field to query 
                    (valid fields: 
                    snapshot_id, start_time, end_time, 
                    url, host, protocol, port, path, status_codes)
        key -- the search key corresponding to the field
        """
        request_body = {field: key} if field else {}
        async with httpx.AsyncClient() as client:
            resp = await self._request(
                client, "QUERY", "/search/files", request_body
            )
            body = self._body_json(resp, 200)
            try:
                return convert_object(
                    [
                        ("snapfilepairs.[]**", SnapshotFilePair),
                        ("**", FileQueryResponse)
                    ],
                    body,
                )
            except Exception as e:
                raise BadResponseError(resp.text) from e

    async def statistics(
        self, intervals: list[Interval]
    ) -> StatisticsResponse:
        """Make a request to the `/statistics` endpoint.

        Arguments:
        intervals -- the interval over which to take the statistics
        """
        async with httpx.AsyncClient() as client:
            resp = await self._request(
                client, "QUERY", "/statistics", {"intervals": intervals}
            )
            body = self._body_json(resp, 200)
            try:
                return convert_object(
                    [
                        ("-[].interval.start**", Timespec),
                        ("-[].interval.end**", Timespec),
                        ("[].interval**", Interval),
                        ("[]**", Statistics),
                        ("", StatisticsResponse),
                    ],
                    body["statistics"],
                )
            except Exception as e:
                raise BadResponseError(resp.text) from e           

