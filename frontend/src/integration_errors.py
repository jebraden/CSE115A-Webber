"""Failures at the UI/service boundary. HTTP errors use the shared API hierarchy."""
import httpx
from .api import APIError

class InvalidArchiveResponse(Exception):
    pass

class BackendUnavailable(Exception):
    pass

def error_text(error):
    if isinstance(error, BackendUnavailable):
        return "Archive service unavailable. Restart Webber and try again."
    if isinstance(error, InvalidArchiveResponse):
        return "Unexpected archive response. Check your archive list before retrying."
    if isinstance(error, httpx.TimeoutException):
        return "Archive request timed out. It may still complete; check your archives before retrying."
    if isinstance(error, httpx.RequestError):
        return "Cannot reach the archive service. Check the backend connection and retry."
    if isinstance(error, APIError):
        message = getattr(error, "message", None)
        if isinstance(message, str) and message.strip():
            return message.strip()[:1000]
    return "Could not complete the request. Check your archives before retrying."

def snapshot_id(result):
    value = result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
    if not isinstance(value, str) or not value.strip():
        raise InvalidArchiveResponse()
    return value
