import pytest
from src.queries import (
    make_snapshot_search_args,
    _copy_if_not_none,
    _SNAPSHOT_QUERY_PARSER,
)
from src.api import Timespec
from PySide6.QtCore import QDateTime, QDate, QTime

# =============================================================================
# Tests for _copy_if_not_none
# =============================================================================


def test_copy_if_not_none_exists_and_not_none():
    """Test that existing non-None values are copied."""
    src = {"key": "value", "other": None}
    dest = {}
    _copy_if_not_none("key", src, dest)
    assert dest == {"key": "value"}


def test_copy_if_not_none_exists_and_is_none():
    """Test that existing None values are not copied."""
    src = {"key": None}
    dest = {}
    _copy_if_not_none("key", src, dest)
    assert dest == {}
    assert "key" not in dest


def test_copy_if_not_none_missing_key_raises():
    """Test that missing keys raise KeyError."""
    src = {"other": "value"}
    dest = {}
    with pytest.raises(KeyError):
        _copy_if_not_none("key", src, dest)


# =============================================================================
# Tests for make_snapshot_search_args - basic queries
# =============================================================================


def test_make_snapshot_search_args_single_word():
    """Test query with single word."""
    result = make_snapshot_search_args("hello")
    assert result["url"] == " *hello *"
    assert "start_time" not in result
    assert "end_time" not in result


def test_make_snapshot_search_args_multiple_words():
    """Test query with multiple words."""
    result = make_snapshot_search_args("hello world test")
    assert result["url"] == " *hello *world *test *"


def test_make_snapshot_search_args_empty_query():
    """Test empty query."""
    result = make_snapshot_search_args("")
    assert "url" not in result


def test_make_snapshot_search_args_whitespace_only():
    """Test whitespace-only query."""
    result = make_snapshot_search_args("   ")
    assert "url" not in result


# =============================================================================
# Tests for make_snapshot_search_args - time keywords
# =============================================================================


def test_make_snapshot_search_args_start_time():
    """Test query with start_time keyword."""
    result = make_snapshot_search_args("hello start_time:'Jan 12 2026'")
    assert result["url"] == " *hello *"
    assert "start_time" in result
    assert isinstance(result["start_time"], Timespec)


def test_make_snapshot_search_args_end_time():
    """Test query with end_time keyword."""
    result = make_snapshot_search_args("hello end_time:'Dec 25 2026'")
    assert result["url"] == " *hello *"
    assert "end_time" in result
    assert isinstance(result["end_time"], Timespec)


def test_make_snapshot_search_args_both_times():
    """Test query with both start_time and end_time."""
    result = make_snapshot_search_args(
        "hello start_time:'Jan 12 2026' end_time:'Dec 25 2026'"
    )
    assert result["url"] == " *hello *"
    assert "start_time" in result
    assert "end_time" in result
    assert isinstance(result["start_time"], Timespec)
    assert isinstance(result["end_time"], Timespec)


def test_make_snapshot_search_args_time_only():
    """Test query with only time keywords (no words)."""
    result = make_snapshot_search_args("start_time:'Jan 12 2026'")
    assert "url" not in result
    assert "start_time" in result


def test_make_snapshot_search_args_time_invalid_format():
    """Test that invalid time format raises QuerySyntaxError."""
    from src.util.queryparse import QuerySyntaxError

    with pytest.raises(QuerySyntaxError):
        make_snapshot_search_args("start_time:invalid")


# =============================================================================
# Tests for make_snapshot_search_args - regexp keyword
# =============================================================================


def test_make_snapshot_search_args_regexp():
    """Test query with regexp keyword."""
    result = make_snapshot_search_args("regexp:https?://example\\.com")
    assert result["url"] == "https?://example\\.com"


def test_make_snapshot_search_args_regexp_with_time():
    """Test query with regexp and time keywords."""
    result = make_snapshot_search_args("regexp:test start_time:'Jan 12 2026'")
    assert result["url"] == "test"
    assert "start_time" in result


def test_make_snapshot_search_args_regexp_with_words_raises():
    """Test that regexp with words raises ValueError."""
    with pytest.raises(
        ValueError,
        match='Query cannot include keywords and the "regexp" attribute together',
    ):
        make_snapshot_search_args("hello regexp:test")
    with pytest.raises(
        ValueError,
        match='Query cannot include keywords and the "regexp" attribute together',
    ):
        make_snapshot_search_args("regexp:test hello")


# =============================================================================
# Tests for make_snapshot_search_args - error cases
# =============================================================================


def test_make_snapshot_search_args_returns_dict():
    """Test that make_snapshot_search_args returns a dict."""
    result = make_snapshot_search_args("test")
    assert isinstance(result, dict)


# =============================================================================
# Tests for make_snapshot_search_args - edge cases
# =============================================================================


def test_make_snapshot_search_args_special_characters():
    """Test query with special characters in words."""
    result = make_snapshot_search_args("test-123 example.org")
    assert result["url"] == " *test\\-123 *example\\.org *"


def test_make_snapshot_search_args_underscore():
    """Test query with underscores (should be treated as word characters)."""
    result = make_snapshot_search_args("snake_case test")
    assert result["url"] == " *snake_case *test *"


def test_make_snapshot_search_args_multiple_spaces():
    """Test query with multiple spaces between words."""
    result = make_snapshot_search_args("hello    world")
    assert result["url"] == " *hello *world *"


def test_make_snapshot_search_args_leading_trailing_spaces():
    """Test query with leading and trailing spaces."""
    result = make_snapshot_search_args("  hello  ")
    assert result["url"] == " *hello *"
