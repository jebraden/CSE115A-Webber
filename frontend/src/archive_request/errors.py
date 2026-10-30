"""Present API failures as plain user messages without coupling to api.py."""
from dataclasses import dataclass

import httpx


class ArchiveServiceUnavailable(Exception):
    """The application has not injected a real archive service yet."""


class InvalidArchiveResponse(Exception):
    """A successful request did not return the required snapshot ID."""


@dataclass(frozen=True)
class ErrorMessage:
    title: str
    detail: str


def _message(error):
    response = getattr(error, "response", None)
    if response is not None:
        try:
            value = response.json().get("message")
        except (ValueError, AttributeError, httpx.StreamError):
            value = None
    else:
        value = getattr(error, "message", None)
    # Never display arbitrary HTML, exception reprs or server tracebacks.
    if isinstance(value, str) and value.strip():
        return value.strip()[:1000]
    return None


def present_error(error: Exception) -> ErrorMessage:
    if isinstance(error, ArchiveServiceUnavailable):
        return ErrorMessage(
            "Archive service is not connected",
            "This build has no connected archive service. Your URL has been kept. "
            "Connect the service and try again.",
        )
    if isinstance(error, InvalidArchiveResponse):
        return ErrorMessage(
            "Unexpected archive response",
            "The service did not return a snapshot ID. Check your archive list before trying again.",
        )
    if isinstance(error, httpx.TimeoutException):
        return ErrorMessage(
            "Archive request timed out",
            "The service took too long to respond. The archive may still have been created. "
            "Check your archive list before retrying.",
        )
    if isinstance(error, httpx.RequestError):
        return ErrorMessage(
            "Cannot reach the archive service",
            "Check that the backend is running and the connection is available. "
            "If the request was already sent, check your archive list before retrying.",
        )
    response = getattr(error, "response", None)
    code = getattr(response, "status_code", None)
    if code is None:
        code = getattr(error, "code", None)
    detail = _message(error)
    if code in (400, 422):
        return ErrorMessage(
            "Archive request rejected",
            detail or "Check the URL and request options, then try again.",
        )
    if code in (401, 403):
        return ErrorMessage(
            "Archive request not permitted",
            detail or "The archive service denied this request. Check access to the service.",
        )
    if code == 404:
        return ErrorMessage(
            "Archive endpoint unavailable",
            detail or "The archive service endpoint could not be found. Check the backend connection.",
        )
    if isinstance(code, int) and 500 <= code <= 599:
        return ErrorMessage(
            "Archive service error",
            detail or "The service could not finish the request. Check your archive list before retrying.",
        )
    return ErrorMessage(
        "Could not archive the URL",
        "An unexpected error occurred. Your URL has been kept. "
        "Check your archive list before trying again.",
    )
