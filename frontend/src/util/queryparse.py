"""
Class for parsing queries with keywords mixed in.
"""

from typing import Callable, Any, NamedTuple, Optional
from enum import Enum, auto


class KeywordKind(Enum):
    """Enum representing possible actions to take when storing keywords."""

    # Replace the previous value
    VALUE = auto()

    # Make a list of all found values
    LIST = auto()


class QueryKeyword:
    """Class representing a parseable keyword."""

    def __init__(
        self,
        name: str,
        default: Any = None,
        kind: KeywordKind = KeywordKind.VALUE,
        parser: Callable[[str], Any] = lambda x: x,
    ):
        self.name = name
        self.kind = kind
        if self.kind == KeywordKind.LIST:
            if default is None:
                default = []
            elif not isinstance(default, list):
                raise TypeError(
                    "Default value of KeywordKind.LIST must be a list"
                )
        self.default = default
        self.parser = parser


class QuerySyntaxError(Exception):
    """Syntax error that occurred while parsing a search query."""

    def __init__(self, text: str, pos: int, length: int, message: str):
        """Construct a query syntax error.

        Arguments:
        text -- the full text of the query
        pos -- the first position of the bad token
        length -- the length of the bad token
        message -- a message describing the error
        """
        self.text = text
        self.pos = pos
        self.length = length
        self.message = message

    def __str__(self) -> str:
        return (
            self.message
            + "\n  "
            + self.text
            + "\n  "
            + (" " * self.pos)
            + ("^" * self.length)
        )


def _read_quoted_string(text: str, start: int, end: int) -> tuple[int, str]:
    quote = text[start]
    backslash = False
    out: list[str] = []
    for i in range(start + 1, end):
        c = text[i]
        if backslash:
            if c == "n":
                out.append("\n")
            elif c == "t":
                out.append("\t")
            else:
                out.append(c)
            backslash = False
        elif c == "\\":
            backslash = True
        elif c == quote:
            break
        else:
            out.append(c)
    if start + 1 == end or text[i] != quote:
        raise QuerySyntaxError(text, start, i - start, "Unterminated string")
        return (len(text), text)
    return (i - start + 1, "".join(out))


def _read_until(
    target: set[str], text: str, start: int, end: int
) -> tuple[str | None, int, str]:
    if start == end:
        return (None, 0, "")
    elif text[start] in {"'", '"'}:
        l, s = _read_quoted_string(text, start, end)
        if start + l >= end:
            return (None, l, s)
        elif text[start + l] in target:
            return (text[start + l], l, s)
        raise QuerySyntaxError(
            text, start + l, end - start - l, "Trailing garbage after string"
        )
    for i in range(start, end):
        if text[i] in target:
            return (text[i], i - start, text[start:i])
    return (None, end - start, text[start:end])


class Word(NamedTuple):
    leading_whitespace: int
    original_length: int
    value: str


class KeywordAndValue(NamedTuple):
    leading_whitespace: int
    original_length: int
    key: str
    value: str


type Term = Word | KeywordAndValue


def _parse_query_term(text: str, start: int, end: int) -> Term | None:
    if start > end:
        raise ValueError("start must be <= end")

    consumed_whitespace = 0
    while start < end and text[start] == " ":
        start += 1
        consumed_whitespace += 1

    # EOS
    if start == end:
        return None

    delim, key_read, key = _read_until({":", " "}, text, start, end)

    if delim != ":":
        return Word(consumed_whitespace, key_read, key)

    _, val_read, val = _read_until({" "}, text, start + key_read + 1, end)

    return KeywordAndValue(
        consumed_whitespace, key_read + 1 + val_read, key, val
    )


class ParsedQuery(NamedTuple):
    """The result of parsing a search query."""

    # Freestanding words in the query
    words: list[str]

    # Key-Value pairs in the query
    keywords: dict[str, Any]


class QueryParser:
    """Class representing a syntax for parsing queries."""

    def __init__(self, keywords: list[QueryKeyword]):
        """Construct a new query parser.

        Arguments:
        keywords -- list of valid keywords
        """
        self.keywords: dict[str, QueryKeyword] = {}
        for kw in keywords:
            self.keywords[kw.name] = kw

    def _get_default_keywords(self) -> dict[str, tuple[bool, Any]]:
        out: dict[str, tuple[bool, Any]] = {}
        for kw in self.keywords.values():
            out[kw.name] = (True, kw.default)
        return out

    def _handle_keyword(
        self,
        words: list[str],
        keywords: dict[str, tuple[bool, Any]],
        text: str,
        start: int,
        length: int,
        key: str,
        val: str,
    ):
        if key in self.keywords:
            kw = self.keywords[key]
            try:
                converted = kw.parser(val)
            except Exception as e:
                raise QuerySyntaxError(
                    text, start, length, "Failed to convert value"
                ) from e
            match kw.kind:
                case KeywordKind.VALUE:
                    keywords[key] = (False, converted)
                case KeywordKind.LIST if keywords[key][0]:
                    keywords[key] = (False, [converted])
                case KeywordKind.LIST:
                    keywords[key][1].append(converted)
        else:
            raise QuerySyntaxError(
                text, start, length, f"Unknown keyword: {key!r}"
            )

    def parse(
        self, text: str, start: Optional[int] = None, end: Optional[int] = None
    ) -> ParsedQuery:
        """Parse a query string.

        Arguments:
        text -- the query string to parse
        start -- the first character (0-indexed, included) to parse in the query
        end -- the last character (0-indexed, excluded) to parse int he query

        Returns: the result of parsing the query
        """
        if start is None:
            start = 0
        if end is None:
            end = len(text)
        words: list[str] = []
        keywords: dict[str, tuple[bool, Any]] = self._get_default_keywords()
        i = start
        while i < end:
            match _parse_query_term(text, i, end):
                case None:
                    break
                case Word(whitespace, length, val):
                    words.append(val)
                    i += whitespace + length
                case KeywordAndValue(whitespace, length, key, val):
                    self._handle_keyword(
                        words, keywords, text, i + whitespace, length, key, val
                    )
                    i += whitespace + length
        return ParsedQuery(words, {k: v for k, (_, v) in keywords.items()})
