"""
Query definitions for the frontend.
"""

from typing import Any

from .util.queryparse import QueryParser, QueryKeyword, KeywordKind
from .util.parsedatetime import parse_timespec
from .api import Timespec

_SNAPSHOT_QUERY_PARSER = QueryParser(
    [
        QueryKeyword(name="start_time", parser=parse_timespec),
        QueryKeyword(name="end_time", parser=parse_timespec),
        QueryKeyword(name="regexp"),
    ],
)


def _copy_if_not_none[V](
    attr: str, src: dict[str, V | None], dest: dict[str, V]
):
    if src[attr] is not None:
        dest[attr] = src[attr]  # type: ignore[assignment]


def make_snapshot_search_args(query: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    res = _SNAPSHOT_QUERY_PARSER.parse(query)
    _copy_if_not_none("start_time", res.keywords, out)
    _copy_if_not_none("end_time", res.keywords, out)
    if res.keywords["regexp"] is not None and res.words:
        raise ValueError(
            'Query cannot include keywords and the "regexp" attribute together'
        )
    elif res.keywords["regexp"] is not None:
        out["url"] = res.keywords["regexp"]
    elif res.words:
        out["url"] = " *" + " *".join(res.words) + " *"
    return out
