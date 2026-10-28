import pytest
from typing import Optional
from src.util.strictnamedtuple import StrictNamedTuple
from copy import copy, deepcopy


# Test fixtures
class Point(StrictNamedTuple):
    x: int
    y: int


class Config(StrictNamedTuple):
    name: str
    verbose: bool = False
    timeout: int = 30


class MixedTypes(StrictNamedTuple):
    text: str
    number: int | str
    optional_val: Optional[int] = None


class ListHolder(StrictNamedTuple):
    items: list[int]
    tags: list[str] = []


class SubclassTest(StrictNamedTuple):
    base_field: str


class ExtendedSubclass(SubclassTest):
    extra: int = 0


def test_basic_construction():
    """Test basic tuple construction with positional args."""
    p = Point(1, 2)
    assert p.x == 1
    assert p.y == 2
    assert p[0] == 1
    assert p[1] == 2
    assert len(p) == 2


def test_positional_and_keyword():
    """Test mixed positional and keyword arguments."""
    p = Point(x=1, y=2)
    assert p.x == 1
    assert p.y == 2

    p2 = Point(1, y=2)
    assert p2.x == 1
    assert p2.y == 2


def test_defaults():
    """Test default values."""
    c = Config("test")
    assert c.name == "test"
    assert c.verbose is False
    assert c.timeout == 30

    c2 = Config("test", verbose=True)
    assert c2.verbose is True
    assert c2.timeout == 30


def test_default_ordering():
    """Test that defaults must be at the end."""
    with pytest.raises(ValueError, match="must have a default value"):

        class BadDefaults(StrictNamedTuple):
            a: int = 5
            b: str


def test_union_typing_union():
    """Test Union type from typing module."""
    m = MixedTypes("hello", 42, None)
    assert m.number == 42

    m2 = MixedTypes("hello", "42", None)
    assert m2.number == "42"

    # Should fail for wrong type
    with pytest.raises(TypeError, match="must be of type"):
        MixedTypes("hello", 3.14, None)


def test_union_types_uniontype():
    """Test PEP 604 union (int | str)."""
    # This should work for both int and str
    MixedTypes("test", 123, None)
    MixedTypes("test", "abc", None)

    # Should fail for float
    with pytest.raises(TypeError):
        MixedTypes("test", 3.14, None)


def test_union_error_message():
    """Test error message for failed union type."""
    with pytest.raises(TypeError) as exc_info:
        MixedTypes("test", 3.14, None)
    assert "int" in str(exc_info.value)


def test_parameterized_list():
    """Test list[int] checking."""
    lh = ListHolder([1, 2, 3])
    assert lh.items == [1, 2, 3]

    with pytest.raises(TypeError, match="items"):
        ListHolder(["not", "ints"])

    with pytest.raises(TypeError):
        ListHolder([[1, 2], [3, 4]])  # list of lists, not list of ints


def test_parameterized_list_nested():
    """Test nested parameterized types."""

    class Nested(StrictNamedTuple):
        data: list[list[int]]

    n = Nested([[1, 2], [3, 4]])
    assert n.data == [[1, 2], [3, 4]]

    with pytest.raises(TypeError):
        Nested([[1, 2], ["a", "b"]])


def test_immutability():
    """Test that instances are immutable."""
    p = Point(1, 2)

    with pytest.raises(
        AttributeError, match="does not support item assignment"
    ):
        p.x = 3

    with pytest.raises(AttributeError, match="does not support item deletion"):
        del p.x


def test_reserved_field_names():
    """Test that computed fields are reserved."""
    with pytest.raises(ValueError, match="reserved"):

        class Bad(StrictNamedTuple):
            _fields: str = "test"


def test_underscore_fields():
    """Test that fields cannot start with underscore."""
    with pytest.raises(ValueError, match='cannot start with "_"'):

        class Bad(StrictNamedTuple):
            _private: int


def test_string_annotations():
    """Test that string annotations are rejected."""
    with pytest.raises(TypeError, match="cannot be a string"):

        class Bad(StrictNamedTuple):
            x: "int"


def test_wrong_arg_count():
    """Test error messages for wrong argument counts."""
    with pytest.raises(TypeError, match="takes 2 arguments"):
        Point(1)

    with pytest.raises(TypeError, match="takes 2 arguments"):
        Point(1, 2, 3)


def test_wrong_arg_count_with_defaults():
    """Test error messages with optional arguments."""
    with pytest.raises(TypeError, match="takes between 1 and 3 arguments"):
        Config()  # Missing required 'name'

    with pytest.raises(TypeError, match="takes between 1 and 3 arguments"):
        Config("test", True, 30, "extra")


def test_unexpected_keyword():
    """Test error for unexpected keyword arguments."""
    with pytest.raises(TypeError, match="unexpected keyword"):
        Point(x=1, y=2, z=3)


def test_multiple_values():
    """Test error for multiple values to same argument."""
    with pytest.raises(TypeError, match="multiple values"):
        Point(1, 2, y=3)

    with pytest.raises(TypeError, match="multiple values"):
        Point(1, 2, x=3)


def test_repr():
    """Test string representation."""
    p = Point(1, 2)
    assert repr(p) == "Point(x=1, y=2)"

    c = Config("test")
    assert repr(c) == "Config(name='test', verbose=False, timeout=30)"


def test_tuple_compatibility():
    """Test that instances behave like tuples."""
    p = Point(1, 2)
    assert isinstance(p, tuple)
    assert p + (3,) == (1, 2, 3)
    assert 1 in p
    assert p.index(2) == 1
    assert p.count(1) == 1


def test_subclassing():
    """Test inheritance from StrictNamedTuple."""
    s = ExtendedSubclass("base", extra=5)
    assert s.base_field == "base"
    assert s.extra == 5
    assert isinstance(s, SubclassTest)


def test_type_error_message_formatting():
    """Test that type error messages are informative."""

    class BadTypes(StrictNamedTuple):
        x: int
        y: str

    with pytest.raises(TypeError) as exc_info:
        BadTypes("not int", "ok")
    assert "x" in str(exc_info.value)
    assert "int" in str(exc_info.value)


def test_empty_tuple():
    """Test empty NamedTuple (no fields)."""

    class Empty(StrictNamedTuple):
        pass

    e = Empty()
    assert len(e) == 0
    assert repr(e) == "Empty()"


def test_sentinel_logic():
    """Test that defaults fill in correctly with kwargs."""

    class Mixed(StrictNamedTuple):
        a: int
        b: str = "default"
        c: int = 0

    m = Mixed(1, c=10)
    assert m.a == 1
    assert m.b == "default"
    assert m.c == 10


def test_multiple_union_types():
    """Test complex union types."""

    class Complex(StrictNamedTuple):
        val: int | str | list[int]

    Complex(42)
    Complex("text")
    Complex([1, 2, 3])

    with pytest.raises(TypeError):
        Complex(3.14)


def test_none_in_union():
    """Test Optional types."""

    class Opt(StrictNamedTuple):
        val: Optional[int] = None

    o = Opt(5)
    o2 = Opt(None)
    o3 = Opt()  # uses default

    assert o.val == 5
    assert o2.val is None
    assert o3.val is None


def test_field_access_after_construction():
    """Test that properties work correctly."""
    p = Point(1, 2)

    # Access via property
    assert p.x == 1
    assert p.y == 2

    # Access via tuple index
    assert p[0] == 1
    assert p[1] == 2

    # Both should be equal
    assert p.x == p[0]


def test_error_messages_are_descriptive():
    """Test that error messages include class name and field info."""
    with pytest.raises(TypeError) as exc_info:
        Point("not int", 2)
    msg = str(exc_info.value)
    assert "Point" in msg or "x" in msg  # Should mention field or class


def test_shallow_copy():
    """Test the shallow copy function."""

    class Test(StrictNamedTuple):
        s1: object
        s2: object

    t = Test(object(), object())
    c = copy(t)
    assert c == t
    assert c is not t


def test_deepcopy():
    """Test the deepcopy function."""

    class Test(StrictNamedTuple):
        s1: object
        s2: object

    t = Test(object(), object())
    c = deepcopy(t)
    assert t[0] is not c[0]
    assert t[1] is not c[1]
    assert c is not t
