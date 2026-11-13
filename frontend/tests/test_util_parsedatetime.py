import os
import pytest
from PySide6.QtCore import QDateTime, QDate, QTime
from src.util.parsedatetime import (
    parse_datetime,
    parse_timespec,
    _interpret_month,
    _parse_integral_thing,
    _days_for_month,
)
from src.api import Timespec
from unittest.mock import patch


@pytest.fixture
def fixed_datetime():
    with patch(
        "src.util.parsedatetime.QDate.currentDate"
    ) as currentDate, patch(
        "src.util.parsedatetime.QDateTime.currentDateTime"
    ) as currentDateTime:
        currentDate.return_value = QDate(2008, 4, 1)
        currentDateTime.return_value = QDateTime(
            currentDate.return_value, QTime(8, 31)
        )
        yield currentDate, currentDateTime


# =============================================================================
# Tests for _interpret_month
# =============================================================================


def test_interpret_month_numeric():
    """Test numeric month parsing."""
    assert _interpret_month("1") == 1
    assert _interpret_month("12") == 12
    assert _interpret_month("012") == 12


def test_interpret_month_full_names():
    """Test full month name parsing (case-insensitive)."""
    assert _interpret_month("January") == 1
    assert _interpret_month("February") == 2
    assert _interpret_month("December") == 12
    assert _interpret_month("january") == 1
    assert _interpret_month("JANUARY") == 1


def test_interpret_month_prefixes():
    """Test abbreviated month names."""
    assert _interpret_month("Jan") == 1
    assert _interpret_month("Feb") == 2
    assert _interpret_month("Mar") == 3
    assert _interpret_month("Apr") == 4
    assert _interpret_month("Aug") == 8


def test_interpret_month_single_char_unambiguous():
    """Test single-char month prefixes that are unambiguous."""
    # 'J' is ambiguous (January, June, July)
    # 'F' uniquely identifies February
    assert _interpret_month("F") == 2
    # 'A' is ambiguous (April, August)
    # 'M' is ambiguous (March, May)
    # 'S' uniquely identifies September
    assert _interpret_month("S") == 9
    # 'O' uniquely identifies October
    assert _interpret_month("O") == 10
    # 'N' uniquely identifies November
    assert _interpret_month("N") == 11
    # 'D' uniquely identifies December
    assert _interpret_month("D") == 12


def test_interpret_month_out_of_range():
    """Test that month numbers out of range raise ValueError."""
    with pytest.raises(ValueError, match="Not a valid month"):
        _interpret_month("0")
    with pytest.raises(ValueError, match="Not a valid month"):
        _interpret_month("13")
    with pytest.raises(ValueError, match="Not a valid month"):
        _interpret_month("-1")


def test_interpret_month_invalid_text():
    """Test that invalid month text raises ValueError."""
    with pytest.raises(ValueError, match="Not a valid month"):
        _interpret_month("xyz")


def test_interpret_month_ambiguous_prefix():
    """Test that ambiguous month prefixes raise ValueError."""
    # 'A' matches April, August
    with pytest.raises(ValueError, match="Not a valid month"):
        _interpret_month("A")
    # 'J' matches January, June, July
    with pytest.raises(ValueError, match="Not a valid month"):
        _interpret_month("J")
    # 'M' matches March, May
    with pytest.raises(ValueError, match="Not a valid month"):
        _interpret_month("M")


# =============================================================================
# Tests for _parse_thing
# =============================================================================


def test_parse_thing_valid():
    """Test valid number parsing within range."""
    assert _parse_integral_thing("hour", "12", 0, 23) == 12
    assert _parse_integral_thing("minute", "0", 0, 59) == 0
    assert _parse_integral_thing("minute", "59", 0, 59) == 59


def test_parse_thing_out_of_range_low():
    """Test that numbers below minimum raise ValueError."""
    with pytest.raises(ValueError, match="Not a valid hour"):
        _parse_integral_thing("hour", "-1", 0, 23)
    with pytest.raises(ValueError, match="Not a valid minute"):
        _parse_integral_thing("minute", "-1", 0, 59)


def test_parse_thing_out_of_range_high():
    """Test that numbers above maximum raise ValueError."""
    with pytest.raises(ValueError, match="Not a valid hour"):
        _parse_integral_thing("hour", "24", 0, 23)
    with pytest.raises(ValueError, match="Not a valid minute"):
        _parse_integral_thing("minute", "60", 0, 59)


def test_parse_thing_invalid_text():
    """Test that non-numeric text raises ValueError."""
    with pytest.raises(ValueError, match="Not a valid hour"):
        _parse_integral_thing("hour", "abc", 0, 23)


# =============================================================================
# Tests for _days_for_month
# =============================================================================


def test_days_for_month_standard():
    """Test days per month for standard years."""
    # 31-day months
    assert _days_for_month(1, 2024) == 31
    assert _days_for_month(3, 2024) == 31
    assert _days_for_month(5, 2024) == 31
    assert _days_for_month(7, 2024) == 31
    assert _days_for_month(8, 2024) == 31
    assert _days_for_month(10, 2024) == 31
    # 30-day months
    assert _days_for_month(4, 2024) == 30
    assert _days_for_month(6, 2024) == 30
    assert _days_for_month(9, 2024) == 30
    assert _days_for_month(11, 2024) == 30


def test_days_for_month_february_leap_year():
    """Test February in leap years."""
    assert _days_for_month(2, 2024) == 29
    assert _days_for_month(2, 2020) == 29
    assert _days_for_month(2, 1996) == 29


def test_days_for_month_february_non_leap():
    """Test February in non-leap years."""
    assert _days_for_month(2, 2023) == 28
    assert _days_for_month(2, 2019) == 28


def test_days_for_month_century_rules():
    """Test century year leap year rules.

    A year is a leap year if:
    - divisible by 4 AND
    - (not divisible by 100 OR divisible by 400)
    """
    # 1900: divisible by 100 but not 400, so NOT a leap year
    assert _days_for_month(2, 1900) == 28
    # 2000: divisible by 400, so IS a leap year
    assert _days_for_month(2, 2000) == 29
    # 1600: divisible by 400, so IS a leap year
    assert _days_for_month(2, 1600) == 29
    # 2100: divisible by 100 but not 400, so NOT a leap year
    assert _days_for_month(2, 2100) == 28


# =============================================================================
# Tests for parse_datetime - special strings
# =============================================================================


def test_parse_datetime_now(fixed_datetime):
    """Test 'now' returns current datetime."""
    result = parse_datetime("now")
    assert result == fixed_datetime[1].return_value


def test_parse_datetime_today(fixed_datetime):
    """Test 'today' returns midnight on current day."""
    result = parse_datetime("today")
    assert result.date() == fixed_datetime[1].return_value.date()
    assert result.time() == QTime(0, 0, 0)


def test_parse_datetime_yesterday(fixed_datetime):
    """Test 'yesterday' returns midnight on previous day."""
    result = parse_datetime("yesterday")
    assert result.date() == fixed_datetime[1].return_value.date().addDays(-1)
    assert result.time() == QTime(0, 0, 0)


def test_parse_datetime_special_string_with_case():
    assert parse_datetime("NOW") == parse_datetime("now")
    assert parse_datetime("yesterday") == parse_datetime("yesterday")
    assert parse_datetime("yesterday") == parse_datetime("yesterday")


# =============================================================================
# Tests for parse_datetime - error handling
# =============================================================================


def test_parse_datetime_empty_string():
    """Test that empty string raises ValueError."""
    with pytest.raises(ValueError, match="Empty datetime string"):
        parse_datetime("")


def test_parse_datetime_whitespace_only():
    """Test that whitespace-only string raises ValueError."""
    with pytest.raises(ValueError, match="Empty datetime string"):
        parse_datetime("   ")
    with pytest.raises(ValueError, match="Empty datetime string"):
        parse_datetime("\t\n")


def test_parse_datetime_invalid_format():
    """Test that unparseable text raises ValueError."""
    with pytest.raises(ValueError, match="Cannot parse datetime"):
        parse_datetime("not a date")
    with pytest.raises(ValueError, match="Cannot parse datetime"):
        parse_datetime("hello world")
    with pytest.raises(ValueError, match="Cannot parse datetime"):
        parse_datetime("12345")


# =============================================================================
# Tests for parse_datetime - date parsing
# =============================================================================


def test_parse_datetime_date_month_name_space():
    """Test date with month name and space separators."""
    result = parse_datetime("Jan 12 2026")
    assert result.date() == QDate(2026, 1, 12)
    assert result.time() == QTime(0, 0, 0)  # Defaults to midnight


def test_parse_datetime_date_month_name_slash():
    """Test date with month name and slash separators."""
    result = parse_datetime("Janu/12/2026")
    assert result.date() == QDate(2026, 1, 12)


def test_parse_datetime_date_numeric_slash():
    """Test date with numeric month and slash separators."""
    result = parse_datetime("1/12/2026")
    assert result.date() == QDate(2026, 1, 12)


def test_parse_datetime_date_numeric_dot():
    """Test date with numeric month and dot separators."""
    result = parse_datetime("01.12.2026")
    assert result.date() == QDate(2026, 1, 12)


def test_parse_datetime_date_all_numeric():
    """Test date with all numeric components."""
    result = parse_datetime("12/25/2026")
    assert result.date() == QDate(2026, 12, 25)


def test_parse_datetime_date_without_year():
    """Test date without year defaults to current year."""
    result = parse_datetime("Jan 15")
    current_year = QDate.currentDate().year()
    assert result.date() == QDate(current_year, 1, 15)


def test_parse_datetime_date_case_insensitive():
    """Test that month names are case-insensitive."""
    result1 = parse_datetime("JAN 12 2026")
    result2 = parse_datetime("jan 12 2026")
    result3 = parse_datetime("Jan 12 2026")
    assert result1.date() == QDate(2026, 1, 12)
    assert result2.date() == QDate(2026, 1, 12)
    assert result3.date() == QDate(2026, 1, 12)


# =============================================================================
# Tests for parse_datetime - time parsing
# =============================================================================


def test_parse_datetime_time_only_uses_current_date(fixed_datetime):
    result = parse_datetime("13:20")
    assert result.date() == fixed_datetime[1].return_value.date()
    assert result.time() == QTime(13, 20)


def test_parse_datetime_time_24h():
    """Test 24-hour time format."""
    result = parse_datetime("13:20")
    assert result.time() == QTime(13, 20)


def test_parse_datetime_time_24h_with_seconds():
    """Test 24-hour time format with seconds."""
    result = parse_datetime("13:20:30")
    assert result.time() == QTime(13, 20, 30)


def test_parse_datetime_time_24h_midnight():
    """Test 24-hour format for midnight."""
    result = parse_datetime("00:00")
    assert result.time() == QTime(0, 0)


def test_parse_datetime_time_24h_max():
    """Test 24-hour format for latest valid time."""
    result = parse_datetime("23:59:59")
    assert result.time() == QTime(23, 59, 59)


def test_parse_datetime_time_12h_am():
    """Test 12-hour AM time format with 'a'."""
    result = parse_datetime("1:20 a")
    assert result.time() == QTime(1, 20)


def test_parse_datetime_time_12h_pm():
    """Test 12-hour PM time format with 'p'."""
    result = parse_datetime("1:20 p")
    assert result.time() == QTime(13, 20)


def test_parse_datetime_time_12h_am_full():
    """Test 12-hour AM time format with 'am'."""
    result = parse_datetime("1:20 am")
    assert result.time() == QTime(1, 20)


def test_parse_datetime_time_12h_pm_full():
    """Test 12-hour PM time format with 'pm'."""
    result = parse_datetime("1:20 pm")
    assert result.time() == QTime(13, 20)


def test_parse_datetime_time_12h_pm_noon():
    """Test 12-hour PM format for noon."""
    result = parse_datetime("12:00 pm")
    assert result.time() == QTime(12, 0)


def test_parse_datetime_time_12h_am_midnight():
    """Test 12-hour AM format for midnight."""
    result = parse_datetime("12:00 am")
    assert result.time() == QTime(0, 0)


# =============================================================================
# Tests for parse_datetime - combined date and time
# =============================================================================


def test_parse_datetime_date_and_time():
    """Test combined date and time."""
    result = parse_datetime("Jan 12 2026 13:20")
    assert result.date() == QDate(2026, 1, 12)
    assert result.time() == QTime(13, 20)


def test_parse_datetime_date_and_time_full():
    """Test combined date and full time with seconds."""
    result = parse_datetime("12/25/2026 14:30:45")
    assert result.date() == QDate(2026, 12, 25)
    assert result.time() == QTime(14, 30, 45)


def test_parse_datetime_date_and_time_12h():
    """Test combined date and 12-hour time."""
    result = parse_datetime("Jan 12 2026 1:20 pm")
    assert result.date() == QDate(2026, 1, 12)
    assert result.time() == QTime(13, 20)


# =============================================================================
# Tests for parse_datetime - whitespace handling
# =============================================================================


def test_parse_datetime_leading_trailing_whitespace():
    """Test leading and trailing whitespace is stripped."""
    result = parse_datetime("  Jan 12 2026  ")
    assert result.date() == QDate(2026, 1, 12)


def test_parse_datetime_internal_spaces():
    """Test multiple internal spaces between parts."""
    result = parse_datetime("Jan    12    2026")
    assert result.date() == QDate(2026, 1, 12)


# =============================================================================
# Tests for parse_datetime - validation errors
# =============================================================================


def test_parse_datetime_invalid_month_name():
    """Test invalid month name raises ValueError."""
    with pytest.raises(ValueError, match="Not a valid month"):
        parse_datetime("xyz 12 2026")


def test_parse_datetime_ambiguous_month_prefix():
    """Test ambiguous month prefix raises ValueError."""
    # 'J' matches January, June, July
    with pytest.raises(ValueError, match="Not a valid month"):
        parse_datetime("J 12 2026")


def test_parse_datetime_day_out_of_range():
    """Test day out of range raises ValueError."""
    with pytest.raises(ValueError, match="Not a valid day"):
        parse_datetime("Jan 0 2026")
    with pytest.raises(ValueError, match="Not a valid day"):
        parse_datetime("Jan 32 2026")


def test_parse_datetime_feb_29_non_leap_year():
    """Test Feb 29 in non-leap year raises ValueError."""
    with pytest.raises(ValueError, match="Not a valid day"):
        parse_datetime("Feb 29 2023")


def test_parse_datetime_feb_29_leap_year():
    """Test Feb 29 in leap year is valid."""
    result = parse_datetime("Feb 29 2024")
    assert result.date() == QDate(2024, 2, 29)


def test_parse_datetime_feb_29_century_non_leap():
    """Test Feb 29 in century non-leap year raises ValueError."""
    with pytest.raises(ValueError, match="Not a valid day"):
        parse_datetime("Feb 29 1900")


def test_parse_datetime_feb_29_century_leap():
    """Test Feb 29 in century leap year is valid."""
    result = parse_datetime("Feb 29 2000")
    assert result.date() == QDate(2000, 2, 29)


def test_parse_datetime_hour_out_of_range():
    """Test hour out of range in 24h format raises ValueError."""
    with pytest.raises(ValueError, match="Not a valid hour"):
        parse_datetime("24:00")


def test_parse_datetime_minute_out_of_range():
    """Test minute out of range raises ValueError."""
    with pytest.raises(ValueError, match="Not a valid minute"):
        parse_datetime("13:60")


# =============================================================================
# Tests for parse_timespec
# =============================================================================


def test_parse_timespec_basic():
    """Test parse_timespec returns Timespec."""
    result = parse_timespec("Jan 12 2026")
    assert isinstance(result, Timespec)
    # Convert back to verify it's a valid time
    dt = result.to_qdatetime()
    assert dt.date() == QDate(2026, 1, 12)


def test_parse_timespec_error_propagation():
    """Test parse_timespec propagates errors from parse_datetime."""
    with pytest.raises(ValueError, match="Cannot parse datetime"):
        parse_timespec("invalid")
    with pytest.raises(ValueError, match="Empty datetime string"):
        parse_timespec("")


# =============================================================================
# Tests for parse_datetime - edge cases
# =============================================================================


def test_parse_datetime_month_boundary():
    """Test parsing at month boundaries."""
    # Month 1 (January) has 31 days
    result = parse_datetime("Jan 31 2026")
    assert result.date() == QDate(2026, 1, 31)

    # Month 4 (April) has 30 days, day 31 should fail
    with pytest.raises(ValueError):
        parse_datetime("Apr 31 2026")


def test_parse_datetime_year_zero():
    """Test year 0 raises ValueError."""
    with pytest.raises(ValueError, match="Not a valid year"):
        parse_datetime("Jan 1 0000")


def test_parse_datetime_year_max():
    """Test year 9999 is valid."""
    result = parse_datetime("Jan 1 9999")
    assert result.date() == QDate(9999, 1, 1)


def test_parse_datetime_year_too_large():
    """Test year > 9999 raises ValueError."""
    with pytest.raises(ValueError, match="Not a valid year"):
        parse_datetime("Jan 1 10000")


def test_parse_datetime_returns_qdatetime():
    """Test that parse_datetime returns QDateTime instance."""
    result = parse_datetime("Jan 12 2026")
    assert isinstance(result, QDateTime)


def test_parse_datetime_different_separators_fail():
    """Test that mixed separators raise ValueError.

    The regex requires both separators to be the same.
    """
    with pytest.raises(ValueError, match="Cannot parse datetime"):
        parse_datetime("1/12.2026")
    with pytest.raises(ValueError, match="Cannot parse datetime"):
        parse_datetime("Jan 12/2026")
