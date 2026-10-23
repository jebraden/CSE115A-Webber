"""
Runtime type checking NamedTuple implementation
"""

from typing import Any, TypeVar, Callable
from types import GenericAlias
from operator import itemgetter
import sys

try:
    import annotationlib

    _have_hannotationlib = True
except ImportError:
    _have_hannotationlib = False

if sys.version_info >= (3, 14):
    from typing import Union
else:
    from types import UnionType as Union


def _get_parent_fields_types(
    obj: type,
) -> tuple[list[str], list[type], list[Any]]:
    fields: list[str] = []
    types: list[type] = []
    defaults: list[Any] = []
    for base in obj.__bases__:
        if hasattr(base, "_fields") and hasattr(base, "_types"):
            if dup := [f for f in base._fields if f in fields]:
                raise TypeError(f"Field {dup[0]} appears more than once")
            fields.extend(base._fields)
            types.extend(base._types)
        if hasattr(base, "_defaults"):
            defaults.extend(base._defaults)
        elif defaults and hasattr(base, "_fields"):
            raise TypeError(
                f"Field {base._fields[-1]!r} on base {base.__name__} must "
                "have a default value"
            )
    return fields, types, defaults


class _StrictNamedTupleMeta(type):
    COMPUTED_FIELDS = ("_fields", "_types", "_defaults")

    def __new__(
        cls,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs,
    ) -> type:
        obj: type = super().__new__(cls, name, bases, namespace, **kwargs)
        if "__annotations__" in namespace:
            annotations = namespace["__annotations__"]
        elif _have_hannotationlib:
            af = annotationlib.get_annotate_from_class_namespace(namespace)
            if af:
                annotations = annotationlib.call_annotate_function(
                    af, annotationlib.Format.FORWARDREF, owner=obj
                )
            else:
                annotations = {}
        else:
            annotations = {}
        for var in annotations.keys():
            if (
                var.startswith("_")
                and not var.startswith("__")
                and var not in _StrictNamedTupleMeta.COMPUTED_FIELDS
            ):
                raise ValueError(
                    'TypedNamedTuple fields cannot start with "_"'
                )
        for special in _StrictNamedTupleMeta.COMPUTED_FIELDS:
            if special in namespace:
                raise ValueError(f"Field name {special!r} is reserved")
        fields, types, defs = _get_parent_fields_types(obj)
        for i, (var, typ) in enumerate(annotations.items(), start=len(fields)):
            if isinstance(typ, str):
                raise TypeError(
                    f"Type annotation for {var!r} cannot be a string"
                )
            if var in _StrictNamedTupleMeta.COMPUTED_FIELDS:
                continue
            fields.append(var)
            types.append(typ)
            if var in namespace:
                defs.append(namespace[var])
            elif defs:
                raise ValueError(f"Field {var!r} must have a default value")
            setattr(obj, var, property(itemgetter(i)))
        setattr(obj, "_fields", tuple(fields))
        setattr(obj, "_types", tuple(types))
        setattr(obj, "_defaults", tuple(defs))
        return obj


_T_co = TypeVar("_T_co", covariant=True)


def _pretty_print_type(t: type) -> str:
    tt = type(t)
    if tt is Union or tt is GenericAlias:
        return str(t)
    else:
        return t.__name__


# Function to check parameterized types
#
# Arguments:
# obj -- the object to check
# type -- the parameterized type to check against
# rec -- recursively check if object is an instance of type
#
# Returns: True if obj is a subtype of type, False otherwise
type ParameterizedChecker = Callable[
    [object, GenericAlias, Callable[[object, type], bool]], bool
]

_parameterized_checkers: dict[type, ParameterizedChecker] = {}


def _get_parameterized_checker(expected: GenericAlias) -> ParameterizedChecker:
    assert isinstance(expected.__origin__, type)
    for cls in expected.__origin__.__mro__:
        if cls in _parameterized_checkers:
            return _parameterized_checkers[cls]
    raise TypeError(f"No checker defined for {expected}")


def _parameterized_isinstance(obj: object, typ: type) -> bool:
    if isinstance(typ, GenericAlias):
        checker = _get_parameterized_checker(typ)
        return checker(obj, typ, _parameterized_isinstance)
    else:
        return isinstance(obj, typ)


def _check_type(name: str, val: Any, expected: type):
    if type(expected) is Union:
        for subtype in expected.__args__:  # type: ignore[attr-defined]
            if _parameterized_isinstance(val, subtype):
                return
        tn = _pretty_print_type(expected)
        raise TypeError(f"Field {name!r} must be of type '{tn}'")
    elif not _parameterized_isinstance(val, expected):
        tn = _pretty_print_type(expected)
        raise TypeError(f"Field {name!r} must be of type '{tn}'")


def define_parameterized_checker(cls: type, checker: ParameterizedChecker):
    """Define checker to be a new checker.

    Arguments:
    cls -- the generic class
    checker -- the checker function
    """
    _parameterized_checkers[cls] = checker


def _check_list(
    val: object, cls: GenericAlias, rec: Callable[[object, type], bool]
) -> bool:
    assert len(cls.__args__) == 1
    if not isinstance(val, list):
        return False
    for thing in val:
        if not rec(thing, cls.__args__[0]):
            return False
    return True


define_parameterized_checker(list, _check_list)


class StrictNamedTuple(tuple, metaclass=_StrictNamedTupleMeta):
    """NamedTuple with runtime type checking.

    StrictNamedTuple can use used as a superclass in the same way NamedTuple
    can. However, it uses the type annotations to perform runtime type
    checking.

    StrictNamedTuple does NOT support the functional syntax that NamedTuple
    does.
    """

    _fields: tuple[str, ...]
    _types: tuple[type, ...]
    _defaults: tuple[Any, ...]

    def __new__(cls, *args: _T_co, **kwargs: _T_co):
        if cls is StrictNamedTuple:
            raise TypeError("StrictNamedTuple() cannot be used directly")
        sentinel = object()
        data: list[object] = list(args)
        missing = len(cls._fields) - len(data)
        data += [sentinel] * missing
        for name, val in kwargs.items():
            if name not in cls._fields:
                raise TypeError(
                    f"{cls.__name__}() got an unexpected keyword "
                    f"argument {name!r}"
                )
            idx = cls._fields.index(name)
            if data[idx] is sentinel:
                data[idx] = val
                missing -= 1
            else:
                raise TypeError(
                    f"{cls.__name__}() got multiple values for "
                    f"argument {name!r}"
                )
        min_default = len(cls._fields) - len(cls._defaults)
        for i, cur in enumerate(data):
            if cur is sentinel and i >= min_default:
                data[i] = cls._defaults[i - min_default]
                missing -= 1
        if missing:
            given = len(args) + len(kwargs)
            copula = "was" if given == 1 else "were"
            min = len(cls._fields) - len(cls._defaults)
            max = len(cls._fields)
            if min == max:
                raise TypeError(
                    f"{cls.__name__}() takes {max} arguments, "
                    f"but {given} {copula} given"
                )
            else:
                raise TypeError(
                    f"{cls.__name__}() takes between {min} and {max} "
                    f"arguments, but {given} {copula} given"
                )
        for i, to_check in enumerate(data):
            _check_type(cls._fields[i], to_check, cls._types[i])
        return super().__new__(cls, data)

    def __repr__(self) -> str:
        tn = type(self).__name__
        out = []
        for i in range(len(self)):
            out.append(f"{self._fields[i]}={self[i]!r}")
        return f"{tn}({", ".join(out)})"

    def __setattr__(self, name: str, value: Any):
        tn = type(self).__name__
        raise AttributeError(f"{tn} object does not support item assignment")

    def __delattr__(self, name: str):
        tn = type(self).__name__
        raise AttributeError(f"{tn} object does not support item deletion")
