import pytest
from src.util.queryparse import (
    KeywordKind,
    QueryKeyword,
    QueryParser,
    QuerySyntaxError,
    ParsedQuery,
    Word,
    KeywordAndValue,
    _parse_query_term,
    _read_quoted_string,
    _read_until,
)


class TestKeywordKind:
    """Tests for the KeywordKind enum."""

    def test_value_exists(self):
        assert KeywordKind.VALUE is not None

    def test_list_exists(self):
        assert KeywordKind.LIST is not None

    def test_distinct_values(self):
        assert KeywordKind.VALUE != KeywordKind.LIST


class TestQueryKeyword:
    """Tests for the QueryKeyword NamedTuple."""

    def test_basic_construction(self):
        kw = QueryKeyword(name="test")
        assert kw.name == "test"
        assert kw.default is None
        assert kw.kind == KeywordKind.VALUE
        assert callable(kw.parser)

    def test_with_custom_parser(self):
        kw = QueryKeyword(name="num", parser=int)
        assert kw.parser("42") == 42

    def test_with_list_kind(self):
        kw = QueryKeyword(name="tags", kind=KeywordKind.LIST)
        assert kw.kind == KeywordKind.LIST

    def test_with_default_value(self):
        kw = QueryKeyword(name="limit", default=10)
        assert kw.default == 10


class TestQuerySyntaxError:
    """Tests for the QuerySyntaxError exception."""

    def test_attributes(self):
        err = QuerySyntaxError("hello world", 6, 5, "Bad token")
        assert err.text == "hello world"
        assert err.pos == 6
        assert err.length == 5
        assert err.message == "Bad token"

    def test_str_formatting(self):
        err = QuerySyntaxError("hello world", 6, 5, "Bad token")
        result = str(err)
        assert "Bad token" in result
        assert "hello world" in result
        assert result.endswith("^" * 5)

    def test_str_caret_position(self):
        err = QuerySyntaxError("hello world", 6, 3, "Bad token")
        result = str(err)
        lines = result.split("\n")
        assert len(lines) == 3
        # Third line should have spaces then carets
        assert lines[2].startswith(" " * 6)
        assert lines[2].endswith("^^^")

    def test_error_string_format(self):
        err = QuerySyntaxError("hello world", 6, 5, "Bad token")
        expected = "Bad token\n  hello world\n        ^^^^^"
        assert str(err) == expected

    def test_error_position_calculation(self):
        text = "abc def"
        err = QuerySyntaxError(text, 4, 3, "Error here")
        result = str(err)
        # Format: message\n  text\n  + pos spaces + length carets
        assert result == "Error here\n  abc def\n      ^^^"

    def test_error_at_start(self):
        err = QuerySyntaxError("text", 0, 4, "Bad start")
        result = str(err)
        assert result == "Bad start\n  text\n  ^^^^"

    def test_error_at_end(self):
        err = QuerySyntaxError("text", 4, 0, "Bad end")
        result = str(err)
        assert result == "Bad end\n  text\n      "


class TestReadQuotedString:
    """Tests for the private _read_quoted_string function."""

    def test_simple_quoted_string(self):
        text = "'hello world'"
        length, content = _read_quoted_string(text, 0, len(text))
        assert length == len(text)
        assert content == "hello world"

    def test_double_quoted_string(self):
        text = '"test string"'
        length, content = _read_quoted_string(text, 0, len(text))
        assert content == "test string"

    def test_single_escape_newline(self):
        text = "'line1\\nline2'"
        length, content = _read_quoted_string(text, 0, len(text))
        assert content == "line1\nline2"

    def test_single_escape_tab(self):
        text = "'col1\\tcol2'"
        length, content = _read_quoted_string(text, 0, len(text))
        assert content == "col1\tcol2"

    def test_multiple_escape_sequences(self):
        """Test that backslash flag resets after each escape."""
        text = "'line1\\nline2\\tend'"
        length, content = _read_quoted_string(text, 0, len(text))
        assert content == "line1\nline2\tend"

    def test_escape_backslash(self):
        text = "'path\\\\to'"
        length, content = _read_quoted_string(text, 0, len(text))
        assert content == "path\\to"

    def test_escaped_quote(self):
        text = "'it\\'s a test'"
        length, content = _read_quoted_string(text, 0, len(text))
        assert content == "it's a test"

    def test_empty_quotes_returns_empty_string(self):
        """Test that empty quotes return an empty string."""
        length, content = _read_quoted_string("''", 0, 2)
        assert length == 2
        assert content == ""

    def test_empty_double_quotes_returns_empty_string(self):
        """Test that empty double quotes return an empty string."""
        length, content = _read_quoted_string('""', 0, 2)
        assert length == 2
        assert content == ""

    def test_unterminated_string_raises(self):
        with pytest.raises(QuerySyntaxError, match="Unterminated string"):
            _read_quoted_string("'hello", 0, 6)


class TestReadUntil:
    """Tests for the private _read_until function."""

    def test_find_delimiter(self):
        delim, length, value = _read_until({":"}, "key:value", 0, 4)
        assert delim == ":"
        assert length == 3
        assert value == "key"

    def test_no_delimiter(self):
        delim, length, value = _read_until({":"}, "hello", 0, 5)
        assert delim is None
        assert length == 5
        assert value == "hello"

    def test_multiple_delimiters(self):
        delim, length, value = _read_until({":", " "}, "hello world", 0, 9)
        assert delim == " "
        assert length == 5
        assert value == "hello"

    def test_start_offset(self):
        delim, length, value = _read_until({":"}, "  key:value", 2, 9)
        assert delim == ":"
        assert length == 3
        assert value == "key"

    def test_single_quoted_string(self):
        """Test that single quotes are detected at any position."""
        delim, length, value = _read_until({" "}, "  'hello' rest", 2, 11)
        assert delim == " "
        assert value == "hello"

    def test_double_quoted_string(self):
        """Test that double quotes are detected."""
        delim, length, value = _read_until({" "}, '  "hello" rest', 2, 12)
        assert delim == " "
        assert value == "hello"

    def test_quoted_string_at_end(self):
        """Test that quoted string at end doesn't raise IndexError."""
        delim, length, value = _read_until({" "}, "'hello'", 0, 7)
        assert delim is None
        assert value == "hello"

    def test_trailing_garbage_after_quote(self):
        """Test error when garbage follows quoted string."""
        with pytest.raises(QuerySyntaxError, match="Trailing garbage"):
            _read_until({" "}, "'hello'x", 0, 8)


class TestParseQueryTerm:
    """Tests for the private _parse_query_term function."""

    def test_single_word(self):
        result = _parse_query_term("hello", 0, 5)
        assert isinstance(result, Word)
        assert result.value == "hello"
        assert result.original_length == 5

    def test_keyword_and_value(self):
        result = _parse_query_term("key:value", 0, 9)
        assert isinstance(result, KeywordAndValue)
        assert result.key == "key"
        assert result.value == "value"

    def test_keyword_with_spaces(self):
        """Note: Values cannot contain spaces - they are delimiters."""
        result = _parse_query_term("key:hello world", 0, 15)
        assert isinstance(result, KeywordAndValue)
        assert result.key == "key"
        # Space is a delimiter, so value stops at first space
        assert result.value == "hello"
        assert result.original_length == 9

    def test_empty_text(self):
        result = _parse_query_term("", 0, 0)
        assert result is None

    def test_invalid_range(self):
        with pytest.raises(ValueError, match="start must be <= end"):
            _parse_query_term("test", 5, 2)

    def test_word_with_delimiter_returns_length_excluding_delimiter(self):
        result = _parse_query_term("hello world", 0, 11)
        assert isinstance(result, Word)
        assert result.value == "hello"
        # Note: length does not include the space delimiter
        assert result.original_length == 5

    def test_leading_whitespace(self):
        """Test that leading whitespace is consumed and counted."""
        result = _parse_query_term("  hello", 0, 7)
        assert isinstance(result, Word)
        assert result.value == "hello"
        assert result.original_length == 7  # includes 2 spaces


class TestParsedQuery:
    """Tests for the ParsedQuery NamedTuple."""

    def test_construction(self):
        pq = ParsedQuery(words=["hello", "world"], keywords={"key": "value"})
        assert pq.words == ["hello", "world"]
        assert pq.keywords == {"key": "value"}


class TestQueryParserBasic:
    """Tests for basic QueryParser functionality."""

    def setup_method(self):
        self.parser = QueryParser([])

    def test_empty_query(self):
        result = self.parser.parse("")
        assert result.words == []
        assert result.keywords == {}

    def test_single_word(self):
        result = self.parser.parse("hello")
        assert result.words == ["hello"]
        assert result.keywords == {}

    def test_single_word_no_delimiter(self):
        result = self.parser.parse("test")
        assert result.words == ["test"]

    def test_multiple_words(self):
        result = self.parser.parse("hello world")
        assert result.words == ["hello", "world"]

    def test_multiple_words_with_spaces(self):
        result = self.parser.parse("  hello   world  ")
        # Leading and trailing spaces are consumed, not stored as empty words
        assert result.words == ["hello", "world"]

    def test_whitespace_only(self):
        result = self.parser.parse("   ")
        assert result.words == []


class TestQueryParserKeywords:
    """Tests for QueryParser with keywords."""

    def test_single_keyword_value(self):
        parser = QueryParser([QueryKeyword(name="key")])
        result = parser.parse("key:value")
        assert result.words == []
        assert result.keywords == {"key": "value"}

    def test_keyword_with_space_after(self):
        parser = QueryParser([QueryKeyword(name="key")])
        result = parser.parse("key:value ")
        assert result.keywords == {"key": "value"}

    def test_multiple_keywords_with_spaces(self):
        parser = QueryParser([QueryKeyword(name="a"), QueryKeyword(name="b")])
        result = parser.parse("a:1 b:2")
        assert result.keywords == {"a": "1", "b": "2"}

    def test_keyword_value_replaced(self):
        parser = QueryParser(
            [QueryKeyword(name="key", kind=KeywordKind.VALUE)]
        )
        result = parser.parse("key:first key:second")
        assert result.keywords == {"key": "second"}

    def test_keyword_value_with_colon(self):
        """Test that colons within values are preserved."""
        parser = QueryParser([QueryKeyword(name="time")])
        result = parser.parse("time:12:30:45")
        assert result.keywords == {"time": "12:30:45"}


class TestQueryParserCustomParser:
    """Tests for QueryParser with custom value parsers."""

    def test_int_parser_value_kind(self):
        """Test that VALUE kind stores the converted value."""
        parser = QueryParser([QueryKeyword(name="num", parser=int)])
        result = parser.parse("num:42")
        assert result.keywords["num"] == 42

    def test_int_parser_list_kind(self):
        """Test that LIST kind stores converted values in a list."""
        parser = QueryParser(
            [QueryKeyword(name="num", parser=int, kind=KeywordKind.LIST)]
        )
        result = parser.parse("num:1 num:2 num:3")
        assert result.keywords["num"] == [1, 2, 3]

    def test_parser_error_raises_syntax_error(self):
        def bad_int(x):
            if not x.isdigit():
                raise ValueError("Not a number")
            return int(x)

        parser = QueryParser([QueryKeyword(name="num", parser=bad_int)])
        with pytest.raises(QuerySyntaxError, match="Failed to convert value"):
            parser.parse("num:hello")

    def test_parser_error_preserves_original_exception(self):
        def bad_parser(x):
            raise ValueError("Invalid number")

        parser = QueryParser([QueryKeyword(name="num", parser=bad_parser)])
        with pytest.raises(QuerySyntaxError) as exc_info:
            parser.parse("num:123")
        assert exc_info.value.__cause__ is not None
        assert str(exc_info.value.__cause__) == "Invalid number"


class TestQueryParserErrors:
    """Tests for QueryParser error handling."""

    def test_unknown_keyword_raises_error(self):
        parser = QueryParser([QueryKeyword(name="known")])
        with pytest.raises(QuerySyntaxError, match="Unknown keyword"):
            parser.parse("unknown:value")

    def test_error_includes_position(self):
        parser = QueryParser([QueryKeyword(name="known")])
        try:
            parser.parse("unknown:value")
            assert False, "Should have raised"
        except QuerySyntaxError as e:
            assert e.text == "unknown:value"
            assert e.pos == 0
            assert e.length == 13

    def test_error_message_shows_caret(self):
        parser = QueryParser([QueryKeyword(name="known")])
        try:
            parser.parse("unknown:value")
            assert False, "Should have raised"
        except QuerySyntaxError as e:
            result = str(e)
            assert "Unknown keyword" in result
            assert "unknown:value" in result
            assert "^^^^^^^^^^^^^" in result


class TestQueryParserStartEnd:
    """Tests for QueryParser with start/end parameters."""

    def setup_method(self):
        self.parser = QueryParser([])

    def test_start_parameter(self):
        result = self.parser.parse("hello world", start=6)
        assert result.words == ["world"]

    def test_end_parameter(self):
        result = self.parser.parse("hello world", end=5)
        assert result.words == ["hello"]

    def test_start_and_end(self):
        result = self.parser.parse("hello world test", start=6, end=11)
        assert result.words == ["world"]

    def test_start_beyond_end(self):
        result = self.parser.parse("hello", start=10)
        assert result.words == []

    def test_start_equals_end(self):
        result = self.parser.parse("hello", start=5, end=5)
        assert result.words == []


class TestQueryParserQuotedStrings:
    """Tests for quoted string support in QueryParser."""

    def test_single_quoted_value(self):
        """Test single-quoted values are parsed correctly."""
        parser = QueryParser([QueryKeyword(name="key")])
        result = parser.parse("key:'hello world'")
        assert result.keywords == {"key": "hello world"}

    def test_double_quoted_value(self):
        """Test double-quoted values are parsed correctly."""
        parser = QueryParser([QueryKeyword(name="key")])
        result = parser.parse('key:"hello world"')
        assert result.keywords == {"key": "hello world"}

    def test_quoted_string_with_spaces(self):
        """Test that spaces inside quotes are preserved."""
        parser = QueryParser([QueryKeyword(name="key")])
        result = parser.parse("key:'hello   world'")
        assert result.keywords == {"key": "hello   world"}

    def test_quoted_string_with_escape(self):
        """Test escape sequences inside quoted strings."""
        parser = QueryParser([QueryKeyword(name="key")])
        result = parser.parse("key:'line1\\nline2'")
        assert result.keywords == {"key": "line1\nline2"}

    def test_quoted_string_at_end(self):
        """Test that quoted string at end doesn't raise IndexError."""
        parser = QueryParser([QueryKeyword(name="key")])
        result = parser.parse("key:'hello'")
        assert result.keywords == {"key": "hello"}

    def test_quoted_string_not_at_start(self):
        """Test that quotes are detected at any position."""
        parser = QueryParser([QueryKeyword(name="key")])
        result = parser.parse("word key:'hello'")
        assert result.keywords == {"key": "hello"}
        assert result.words == ["word"]


class TestQueryParserIntegration:
    """Integration tests for complex query parsing."""

    def test_keyword_then_word(self):
        parser = QueryParser([QueryKeyword(name="type")])
        result = parser.parse("type:test word")
        assert result.words == ["word"]
        assert result.keywords == {"type": "test"}

    def test_word_then_keyword(self):
        parser = QueryParser([QueryKeyword(name="type")])
        result = parser.parse("word type:test")
        assert result.words == ["word"]
        assert result.keywords == {"type": "test"}

    def test_multiple_keywords(self):
        parser = QueryParser(
            [QueryKeyword(name="color"), QueryKeyword(name="size")]
        )
        result = parser.parse("color:red size:L")
        assert result.keywords == {"color": "red", "size": "L"}


class TestParsedQueryStructure:
    """Tests verifying the structure of returned ParsedQuery objects."""

    def test_returns_parsedquery(self):
        parser = QueryParser([])
        result = parser.parse("test")
        assert isinstance(result, ParsedQuery)

    def test_words_is_list(self):
        parser = QueryParser([])
        result = parser.parse("a")
        assert isinstance(result.words, list)

    def test_keywords_is_dict(self):
        parser = QueryParser([QueryKeyword(name="key")])
        result = parser.parse("key:value")
        assert isinstance(result.keywords, dict)


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_query_with_colon_no_value(self):
        parser = QueryParser([QueryKeyword(name="key")])
        result = parser.parse("key:")
        assert result.keywords == {"key": ""}

    def test_query_with_empty_value(self):
        parser = QueryParser([QueryKeyword(name="key")])
        result = parser.parse("key:value")
        assert result.keywords["key"] == "value"

    def test_multiple_colons(self):
        parser = QueryParser([QueryKeyword(name="key")])
        result = parser.parse("key:a:b")
        # The colon after 'a' is part of the value
        assert result.keywords["key"] == "a:b"

    def test_whitespace_only(self):
        parser = QueryParser([])
        result = parser.parse("   ")
        assert result.words == []

    def test_tab_character_in_value(self):
        parser = QueryParser([QueryKeyword(name="key")])
        result = parser.parse("key:hello\tworld")
        # Tab is treated as a regular character in values
        assert result.keywords["key"] == "hello\tworld"

    def test_consecutive_colons(self):
        parser = QueryParser([QueryKeyword(name="key")])
        result = parser.parse("key::value")
        assert result.keywords["key"] == ":value"

    def test_empty_string_query(self):
        parser = QueryParser([])
        result = parser.parse("")
        assert result.words == []
        assert result.keywords == {}

    def test_single_character(self):
        parser = QueryParser([])
        result = parser.parse("a")
        assert result.words == ["a"]

    def test_very_long_query(self):
        parser = QueryParser([])
        words = [f"word{i}" for i in range(100)]
        query = " ".join(words)
        result = parser.parse(query)
        assert len(result.words) == 100


class TestKeywordKindBehavior:
    """Tests for different KeywordKind behaviors."""

    def test_value_kind_replaces(self):
        """Test that VALUE kind replaces the previous value."""
        parser = QueryParser(
            [QueryKeyword(name="key", kind=KeywordKind.VALUE)]
        )
        result = parser.parse("key:first key:second")
        assert result.keywords["key"] == "second"

    def test_list_kind_appends(self):
        """Test that LIST kind appends to a list."""
        parser = QueryParser([QueryKeyword(name="key", kind=KeywordKind.LIST)])
        result = parser.parse("key:first key:second")
        assert result.keywords["key"] == ["first", "second"]

    def test_list_kind_stores_converted(self):
        """Test that LIST kind stores converted values, not raw strings."""
        parser = QueryParser(
            [QueryKeyword(name="num", kind=KeywordKind.LIST, parser=int)]
        )
        result = parser.parse("num:1 num:2 num:3")
        assert result.keywords["num"] == [1, 2, 3]


class TestDefaultValueSystem:
    """Tests for the default value system in QueryParser."""

    def test_default_value_none_by_default(self):
        """Test that keywords default to None when not specified."""
        parser = QueryParser([QueryKeyword(name="key")])
        result = parser.parse("hello")
        assert "key" in result.keywords
        assert result.keywords["key"] is None

    def test_custom_default_value(self):
        """Test that custom default values are used when keyword not specified."""
        parser = QueryParser([QueryKeyword(name="limit", default=10)])
        result = parser.parse("hello")
        assert result.keywords["limit"] == 10

    def test_default_value_string(self):
        """Test default value with a string."""
        parser = QueryParser([QueryKeyword(name="mode", default="normal")])
        result = parser.parse("hello")
        assert result.keywords["mode"] == "normal"

    def test_default_value_overridden_by_query(self):
        """Test that query values override defaults."""
        parser = QueryParser(
            [QueryKeyword(name="limit", default=10, parser=int)]
        )
        result = parser.parse("limit:5")
        assert result.keywords["limit"] == 5

    def test_multiple_defaults(self):
        """Test multiple keywords with different defaults."""
        parser = QueryParser(
            [
                QueryKeyword(name="limit", default=10),
                QueryKeyword(name="offset", default=0),
                QueryKeyword(name="mode", default="normal"),
            ]
        )
        result = parser.parse("hello")
        assert result.keywords["limit"] == 10
        assert result.keywords["offset"] == 0
        assert result.keywords["mode"] == "normal"

    def test_default_value_not_overridden_partially(self):
        """Test that defaults for other keywords are preserved when one is set."""
        parser = QueryParser(
            [
                QueryKeyword(name="limit", default=10, parser=int),
                QueryKeyword(name="offset", default=0),
            ]
        )
        result = parser.parse("limit:5")
        assert result.keywords["limit"] == 5
        assert result.keywords["offset"] == 0

    def test_default_value_empty_query(self):
        """Test that defaults are present even for empty queries."""
        parser = QueryParser([QueryKeyword(name="key", default="value")])
        result = parser.parse("")
        assert result.keywords["key"] == "value"

    def test_default_value_with_words(self):
        """Test that defaults are present when query has words."""
        parser = QueryParser([QueryKeyword(name="key", default="value")])
        result = parser.parse("hello world")
        assert result.words == ["hello", "world"]
        assert result.keywords["key"] == "value"

    def test_default_value_list_kind(self):
        """Test that LIST kind starts with default value when provided."""
        parser = QueryParser(
            [
                QueryKeyword(
                    name="tags", default=["default"], kind=KeywordKind.LIST
                )
            ]
        )
        result = parser.parse("tags:new")
        # LIST kind replaces the default with a list when used
        assert result.keywords["tags"] == ["new"]

    def test_default_value_not_in_list(self):
        """Test that default value is not prepended to LIST kind results."""
        parser = QueryParser(
            [
                QueryKeyword(
                    name="tags", default=["default"], kind=KeywordKind.LIST
                )
            ]
        )
        result = parser.parse("")
        # When not used, the default should be preserved
        assert result.keywords["tags"] == ["default"]

    def test_default_value_none_explicit(self):
        """Test that explicit None default works."""
        parser = QueryParser([QueryKeyword(name="key", default=None)])
        result = parser.parse("hello")
        assert result.keywords["key"] is None

    def test_default_value_falsy_values(self):
        """Test that falsy defaults (0, empty string, False) are preserved."""
        parser = QueryParser(
            [
                QueryKeyword(name="count", default=0),
                QueryKeyword(name="text", default=""),
                QueryKeyword(name="flag", default=False),
            ]
        )
        result = parser.parse("hello")
        assert result.keywords["count"] == 0
        assert result.keywords["text"] == ""
        assert result.keywords["flag"] is False

    def test_default_value_with_parser(self):
        """Test that default values are not passed through the parser."""
        parser = QueryParser(
            [QueryKeyword(name="num", default=42, parser=int)]
        )
        result = parser.parse("hello")
        # Default should be the raw value, not parsed
        assert result.keywords["num"] == 42

    def test_default_value_complex_objects(self):
        """Test that complex objects can be defaults."""
        default_list = [1, 2, 3]
        parser = QueryParser(
            [QueryKeyword(name="items", default=default_list)]
        )
        result = parser.parse("hello")
        assert result.keywords["items"] == [1, 2, 3]

    def test_get_default_keywords_method(self):
        """Test the _get_default_keywords helper method."""
        parser = QueryParser(
            [
                QueryKeyword(name="a", default=1),
                QueryKeyword(name="b", default="text"),
                QueryKeyword(name="c"),  # defaults to None
            ]
        )
        defaults = parser._get_default_keywords()
        assert defaults == {
            "a": (True, 1),
            "b": (True, "text"),
            "c": (True, None),
        }
