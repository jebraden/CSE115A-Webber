"""
Object Conversion Functions
"""

from typing import Any
from collections.abc import Callable, Iterable
from copy import deepcopy


def convpath(
    obj: Any, path: str | list[str], conv: Callable[[Any], Any]
) -> Any:
    """Convert the end of a single path.

    This function will destructively mutate `obj`. However, if the path is ""
    (meaning convert the toplevel), this will return `conv(obj)`. Therefore,
    you should always save the return value of this function.

    Arguments:
    obj -- the object to process
    path -- The path to process (same style as `convert_object`). This does not
            support the "-", "*", or "**" magic strings that `convert_object`
            does.
    conv -- the conversion function to call

    Returns: the converted object
    """
    root = obj
    if not path:
        return conv(obj)
    if isinstance(path, str):
        parts = path.split(".")
    else:
        parts = path
    for i, part in enumerate(parts[:-1]):
        if part == "[]":
            rest = parts[i + 1 :]
            for i, subobj in enumerate(obj):
                obj[i] = convpath(subobj, rest, conv)
            return root
        try:
            obj = obj[part]
        except Exception:
            obj = getattr(obj, part)
    if parts[-1] == "[]":
        for i, subobj in enumerate(obj):
            obj[i] = conv(subobj)
    else:
        try:
            obj[parts[-1]] = conv(obj[parts[-1]])
        except Exception:
            setattr(obj, parts[-1], conv(getattr(obj, parts[-1])))
    return root


class _Path:
    def __init__(self, path: str):
        self.ignore_errors = path.startswith("-")
        if self.ignore_errors:
            path = path[1:]
        self.splice_dict = path.endswith("**")
        self.splice_list = not self.splice_dict and path.endswith("*")
        if self.splice_dict:
            path = path[:-2]
        elif self.splice_list:
            path = path[:-1]
        self.path = path

    def _make_conv_wrapper(self, conv: Callable) -> Callable:
        if self.splice_dict:
            return lambda x: conv(**x)
        elif self.splice_list:
            return lambda x: conv(*x)
        else:
            return conv

    def convert(self, obj: Any, conv: Callable) -> Any:
        cf = self._make_conv_wrapper(conv)
        if self.ignore_errors:
            try:
                return convpath(obj, self.path, cf)
            except Exception:
                return obj
        else:
            return convpath(obj, self.path, cf)


def convert_object(
    paths: Iterable[tuple[str, Callable]], obj: object, copy: bool = True
) -> Any:
    """Convert a complex object.

    The `paths` argument should be an `Iterable` of the form:
      [("x.y", Type), ("x", OtherType), ("", ToplevelType)]
    This will first convert `resp.x.y` into `Type`, then `resp.x` into
    `OtherType`, and finally, `resp` into `ToplevelType`.

    A path component can also be "[]". In this case, the conversion is applied
    to the elements of the path. For example:
      ("x.[].y", Type)
    Will apply `Type` to the `y` path of each element in the iterable value of
    `x`. So, this:
      _convert_response([("x.[].y", int)], {"x": [{"y": "123"}, {"y": 456}]})
    yields:
      {'x': [{'y': 123}, {'y': 456}]}

    Optionally, any path can end with "*" or "**". This indicates that the type
    should be constructed with the decomposed (by either * or **) version of
    the contents of the path. For example:
      ("x.y*", Type)
    will construct `Type` as `Type(*resp.x.y)` rather than `Type(resp.x.y)`.

    Any path can also start with "-". In this case, errors during the
    processing of this path will be silently ignored.

    This does not do type checking, and will raise errors in all sorts of
    cases. It is probably smart to wrap this in a try-catch for all Exceptions
    if you are passing in untrusted data.

    Note that if any of the paths are empty (e.g. named the toplevel object),
    the object may end up being copied, even if `copy=False`. If this is a
    problem, make sure you save the return value from this.

    Arguments:
    paths -- list of paths and the callable to convert them to
    obj -- the object to convert
    copy -- whether or not to `deepcopy` the object before conversion

    Returns: the converted response
    """
    if copy:
        obj = deepcopy(obj)

    for path_str, conv in paths:
        path = _Path(path_str)
        obj = path.convert(obj, conv)
    return obj
