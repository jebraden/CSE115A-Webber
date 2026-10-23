import pytest
from typing import Any
from src.util.convpath import convpath, convert_object


def test_convpath_basic_dict():
    """Test basic path conversion on dict."""
    data = {"x": {"y": "123"}}
    result = convpath(data, "x.y", int)
    assert result["x"]["y"] == 123
    assert result is data  # Returns root


def test_convpath_basic_object():
    """Test basic path conversion on object attributes."""

    class Point:
        def __init__(self):
            self.x = 10
            self.y = 20

    p = Point()
    result = convpath(p, "x", lambda x: x * 2)
    assert result.x == 20
    assert result is p


def test_convpath_empty_path():
    """Test that empty path converts the whole object."""
    data = {"a": 1, "b": 2}
    result = convpath(data, "", lambda x: {"modified": x})
    assert result == {"modified": {"a": 1, "b": 2}}
    assert result is not data  # Returns new object


def test_convpath_nested_path():
    """Test deeply nested path conversion."""
    data = {"a": {"b": {"c": "hello"}}}
    convpath(data, "a.b.c", lambda x: x.upper())
    assert data["a"]["b"]["c"] == "HELLO"


def test_convpath_mixed_dict_and_object():
    """Test path mixing dict access and attribute access."""

    class Inner:
        def __init__(self):
            self.val = "low"

    class Outer:
        def __init__(self):
            self.inner = Inner()

    outer = Outer()
    convpath(outer, "inner.val", lambda x: x.upper())
    assert outer.inner.val == "LOW"


def test_convpath_list_iteration():
    """Test [] path component for list iteration."""
    data = {"items": [{"x": "1"}, {"x": "2"}]}
    convpath(data, "items.[].x", int)
    assert data["items"][0]["x"] == 1
    assert data["items"][1]["x"] == 2


def test_convpath_list_iteration_at_end():
    """Test [] at end of path."""
    data = {"items": [1, 2]}
    convpath(data, "items.[]", lambda x: x * 2)
    assert data["items"][0] == 2
    assert data["items"][1] == 4


def test_path_splice_list():
    """Test * suffix for positional argument splicing."""
    data = {"args": [1, 2, 3]}

    def tuple_maker(*args):
        return ("tuple", *args)

    result = convert_object([("args*", tuple_maker)], data)
    assert result["args"] == ("tuple", 1, 2, 3)


def test_path_splice_dict():
    """Test ** suffix for keyword argument splicing."""
    data = {"kwargs": {"a": 1, "b": 2}}

    def obj_maker(**kwargs):
        return ("obj", kwargs)

    result = convert_object([("kwargs**", obj_maker)], data)
    assert result["kwargs"] == ("obj", {"a": 1, "b": 2})


def test_path_ignore_errors():
    """Test - prefix suppresses conversion errors."""
    data = {"good": "123", "bad": "not_a_number"}
    result = convert_object(
        [("good", int), ("-bad", int)], data  # Should fail silently
    )
    assert result["good"] == 123
    assert result["bad"] == "not_a_number"  # Unchanged


def test_path_ignore_errors_nested():
    """Test error suppression on nested paths."""
    data = {"a": {"b": 123}, "c": {"d": "error"}}
    result = convert_object(
        [("a.b", int), ("-c.d", int)], data  # Should fail silently
    )
    assert result["a"]["b"] == 123
    assert result["c"]["d"] == "error"


def test_convert_object_multiple_paths():
    """Test that convert_object applies paths in order."""
    data = {"x": "10", "y": {"z": "20"}}
    result = convert_object(
        [
            ("x", int),
            ("y.z", int),
        ],
        data,
    )
    assert result["x"] == 10
    assert result["y"]["z"] == 20


def test_convert_object_toplevel():
    """Test converting the top level with empty path."""
    data = {"a": 1}
    result = convert_object([("", lambda x: {"wrapped": x})], data)
    assert result == {"wrapped": {"a": 1}}


def test_convert_object_default_copy():
    """Test that original object is not mutated by default."""
    original = {"x": 1}
    convert_object([("x", lambda x: x + 1)], original)
    assert original["x"] == 1  # Should be unchanged


def test_convert_object_no_copy():
    """Test that copy=False mutates the original object."""
    original = {"x": 1}
    result = convert_object([("x", lambda x: x + 1)], original, copy=False)
    assert original["x"] == 2  # Should be mutated
    assert result is original  # Returns the same object


def test_convert_object_no_copy_toplevel_conversion():
    """Test edge case: copy=False with top-level conversion.

    When converting the top level with empty path, the object may be
    copied even with copy=False because convpath returns conv(obj).
    """
    original = {"a": 1}
    result = convert_object(
        [("", lambda x: {"wrapped": x})], original, copy=False
    )
    # result is the new wrapped object, original is unchanged
    assert result == {"wrapped": {"a": 1}}
    assert original == {"a": 1}
    assert (
        result is not original
    )  # Different object due to top-level conversion


def test_convpath_missing_key_raises():
    """Test that missing keys raise exceptions (not suppressed)."""
    data = {"a": 1}
    with pytest.raises(AttributeError):
        convpath(data, "missing", int)


def test_convpath_list_iteration_complex():
    """Test [] with complex nested paths."""
    data = {
        "users": [{"name": "Alice", "age": "30"}, {"name": "Bob", "age": "25"}]
    }
    convpath(data, "users.[].age", int)
    assert data["users"][0]["age"] == 30
    assert data["users"][1]["age"] == 25


def test_path_splice_list_empty():
    """Test * with empty list."""
    data: dict[str, Any] = {"args": []}

    def maker(*args):
        return args

    result = convert_object([("args*", maker)], data)
    assert result["args"] == ()


def test_path_splice_dict_empty():
    """Test ** with empty dict."""
    data: dict[str, Any] = {"kwargs": {}}

    def maker(**kwargs):
        return kwargs

    result = convert_object([("kwargs**", maker)], data)
    assert result["kwargs"] == {}
