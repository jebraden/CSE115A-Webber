"""Error presentation follows backend response semantics, not URL guesses."""
import httpx
import pytest

from frontend.src.archive_request.errors import (
    ArchiveServiceUnavailable, InvalidArchiveResponse, present_error,
)


def http_error(code, body=None, *, text=None):
    request = httpx.Request("POST", "http://service.test/snapshots/create")
    response = httpx.Response(code, json=body, text=text, request=request)
    return httpx.HTTPStatusError("Request failed", request=request, response=response)


def test_team_api_error_contract_without_importing_unmerged_api_module():
    class BadRequestError(Exception):
        code = 400
        message = "Invalid URL: include a scheme."
    message = present_error(BadRequestError())
    assert message.title == "Archive request rejected"
    assert message.detail == "Invalid URL: include a scheme."


@pytest.mark.parametrize("code", [400, 422])
def test_backend_message_is_preserved_for_validation(code):
    message = present_error(http_error(code, {"message": "Only HTTP(S) URLs are accepted."}))
    assert message.title == "Archive request rejected"
    assert message.detail == "Only HTTP(S) URLs are accepted."


@pytest.mark.parametrize("code, title", [
    (401, "Archive request not permitted"),
    (403, "Archive request not permitted"),
    (404, "Archive endpoint unavailable"),
    (500, "Archive service error"),
    (503, "Archive service error"),
])
def test_server_errors_are_not_presented_as_invalid_urls(code, title):
    message = present_error(http_error(code, {"message": "Backend detail"}))
    assert message.title == title
    assert message.detail == "Backend detail"


@pytest.mark.parametrize("payload", [{}, {"message": None}, {"message": []}, {"message": " "}, []])
def test_malformed_error_payload_has_safe_fallback(payload):
    message = present_error(http_error(400, payload))
    assert "Check the URL" in message.detail


def test_html_error_page_is_not_exposed_as_backend_message():
    message = present_error(http_error(500, text="<html>Traceback: SECRET INTERNAL PATH</html>"))
    assert "SECRET" not in message.detail
    assert "<html>" not in message.detail


def test_timeout_mentions_uncertain_creation_before_retry():
    message = present_error(httpx.ReadTimeout("private debugging detail"))
    assert message.title == "Archive request timed out"
    assert "may still have been created" in message.detail
    assert "private" not in message.detail


def test_connection_error_gives_backend_action():
    message = present_error(httpx.ConnectError("private address"))
    assert message.title == "Cannot reach the archive service"
    assert "backend is running" in message.detail


@pytest.mark.parametrize("error", [ArchiveServiceUnavailable(), InvalidArchiveResponse(), RuntimeError("private traceback")])
def test_non_backend_errors_are_actionable_and_do_not_leak_exception_text(error):
    message = present_error(error)
    assert message.title and message.detail
    assert "private traceback" not in message.detail


def test_long_error_message_is_bounded():
    message = present_error(http_error(400, {"message": "x" * 10000}))
    assert len(message.detail) == 1000
