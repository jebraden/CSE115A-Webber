"""
General purpose date/time string parser.
"""

from PySide6.QtCore import QDate, QTime, QDateTime
import re
from ..api import Timespec


def _interpret_month(text: str) -> int:
    try:
        intval = int(text)
        if intval < 1 or intval > 12:
            raise ValueError(f"Month out of range: {text}")
        return intval
    except ValueError:
        CANDIDATES = [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ]
        found = []
        text = text.lower()
        for i, cand in enumerate(CANDIDATES):
            if cand.startswith(text):
                found.append(i + 1)
        if len(found) == 1:
            return found[0]
        raise ValueError(f"Not a valid month: {text!r}")


def _parse_integral_thing(thing: str, text: str, min: int, max: int) -> int:
    try:
        val = int(text)
        if val < min or val > max:
            raise ValueError(f"{thing.capitalize()} out of range: {text!r}")
        return val
    except ValueError:
        raise ValueError(f"Not a valid {thing}: {text!r}")


def _build_regex(date_regex: str, time_regex: str) -> re.Pattern:
    return re.compile(
        f"\\A({date_regex})?(?:(?(1) ){time_regex})?\\z",
        re.DOTALL | re.IGNORECASE,
    )


_DATETIME_RE = _build_regex(
    "(?P<month>[a-z0-9]+) *(?P<datesep>[/ .]) *(?P<day>[0-9]+)(?: *(?P=datesep) *(?P<year>[0-9]+))?",
    "(?P<hour>[0-9]+) *: *(?P<minute>[0-9]+)(?: *: *(?P<second>[0-9]+))?(?: +(?P<ampm>[ap])m?)?",
)


def _days_for_month(m: int, y: int) -> int:
    if m == 2:
        return 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28
    elif m in {1, 3, 5, 7, 8, 10}:
        return 31
    else:
        return 30


def _interpret_match_groupdict(
    month: str | None,
    day: str | None,
    year: str | None,
    hour: str | None,
    minute: str | None,
    second: str | None,
    ampm: str | None,
    **_kwargs: str | None,
) -> QDateTime:
    if month and day:
        mnum = _interpret_month(month)
        if year:
            ynum = _parse_integral_thing("year", year, 1, 9999)
        else:
            ynum = QDate.currentDate().year()
        dnum = _parse_integral_thing(
            "day", day, 1, _days_for_month(mnum, ynum)
        )
        date = QDate(ynum, mnum, dnum)
    else:
        date = QDate.currentDate()
    if hour and minute:
        if ampm is None:
            hnum = _parse_integral_thing("hour", hour, 0, 23)
        else:
            hnum = _parse_integral_thing("hour", hour, 1, 12) % 12
            if ampm.lower() == "p":
                hnum += 12
        mnum = _parse_integral_thing("minute", minute, 0, 59)
        snum = 0
        if second:
            snum = _parse_integral_thing("second", second, 0, 59)
        time = QTime(hnum, mnum, snum)
    else:
        time = QTime(0, 0, 0)
    return QDateTime(date, time)


def parse_datetime(text: str) -> QDateTime:
    """Parse a string into a QDateTime in the local timezone.

    The string can start and/or end with any number of spaces.

    Dates look like the following (all of these are the same date):
    - Jan 12 2026
    - Janu/12/2026
    - 1/12/2026
    - 01.12.2026

    Note that:
    - Both the first and second separator must be the same
    - There can be any number of spaces between separators and numbers/month names
    - The month name can be any unambiguous (unique) prefix of its full English name

    Times look like the following (all of these are the same time):
    - 13:20
    - 13:20:00
    - 1:20 p
    - 1:20 pm

    If a string doesn't include a date, the output date defaults to the current
    date. If the string doesn't include a time, the output time defaults to
    midnight.

    The following special strings are also recognized:
    - "now": the current time
    - "today": midnight on the current day
    - "yesterday": midnight on the previous day

    Arguments:
    text -- the string to parse

    Returns: the parsed QDateTime
    """
    text = text.strip().lower()
    if not text:
        raise ValueError('Empty datetime string: ""')
    if text == "now":
        return QDateTime.currentDateTime()
    elif text == "today":
        return QDateTime(QDate.currentDate(), QTime(0, 0, 0))
    elif text == "yesterday":
        return QDateTime(QDate.currentDate().addDays(-1), QTime(0, 0, 0))
    match = re.match(_DATETIME_RE, text)
    if match:
        return _interpret_match_groupdict(**match.groupdict())
    raise ValueError(f"Cannot parse datetime: {text!r}")


def parse_timespec(text: str) -> Timespec:
    """Parse a string into a Timespec.

    See `parse_datetime` for more information about the format of the input
    string.

    Arguments:
    text -- the string to parse

    Returns: the parsed timespec
    """
    return Timespec.from_qdatetime(parse_datetime(text).toUTC())
