"""
URL Rewriting Code

This file contains code that parses HTML/CSS documents and normalizes all URLs
so the document
"""

import tinycss2
from bs4 import BeautifulSoup, Tag
import urllib.parse
from pathlib import PurePosixPath
from typing import NamedTuple, Optional
from abc import ABC, abstractmethod


def get_split_result_port(parsed: urllib.parse.ParseResult) -> Optional[int]:
    """Try to extract the port from a parsed URL.

    Return None if the port was not a number.
    """
    try:
        return parsed.port
    except ValueError:
        return None


def construct_netloc(username, password, hostname, port):
    """Construct a URL netloc from parts.

    Any of the parts can be None.
    """
    out = ""
    if username is not None:
        out += username
        if password is not None:
            out += ":" + password
        out += "@"
    out += hostname
    if port is not None:
        out += str(port)
    return out


def normalize_netloc_port(parsed: urllib.parse.ParseResult) -> str:
    """Maybe remove a netloc port if it is redundant with the scheme."""
    scheme = parsed.scheme.lower()
    port = get_split_result_port(parsed)
    if (scheme == "http" and port == 80) or (
        scheme == "https" and port == 443
    ):
        return construct_netloc(
            parsed.username, parsed.password, parsed.hostname, None
        )
    else:
        return parsed.netloc


def build_prefix(parsed: urllib.parse.ParseResult) -> str:
    """Build a URL encoded path component from a URLs scheme and netloc."""
    netloc = normalize_netloc_port(parsed)
    scheme = parsed.scheme.lower()
    return urllib.parse.quote(scheme + "://" + netloc, safe="")


class PathComponent(NamedTuple):
    file: str
    seperator: str


def split_path_preserving_seperators(path: str) -> list[PathComponent]:
    """Parse an HTTP path, preserving the number of '/'s between components."""
    out = []
    file = ""
    seperator = ""
    for c in path:
        if c == "/":
            seperator += "/"
        elif not seperator:
            file += c
        else:
            out.append(PathComponent(file, seperator))
            file = c
            seperator = ""
    if file or seperator:
        out.append(PathComponent(file, seperator))
    return out


def normalize_path(parts: list[PathComponent]) -> list[PathComponent]:
    """Remove '.' and '..' from an HTTP path."""
    out = []
    for i in range(len(parts)):
        part = parts[i]
        if part.file == "..":
            # just ignore if the path starts with ".."
            if len(out) > 1:
                out.pop()
        elif part.file != ".":
            out.append(part)
    return out


def join_path_components(parts: list[PathComponent]) -> str:
    """Join a list of PathComponents into a string path."""
    return "".join(map(lambda part: part.file + part.seperator, parts))


def concat_path_components(
    parts1: list[PathComponent], parts2: list[PathComponent]
) -> list[PathComponent]:
    """Resolve parts2 against parts1.

    If parts2 is absolute, just return it.
    """
    if parts2 and not parts2[0].file:  # parts2 is absolute
        return parts2

    if not parts1:
        parts1 = [PathComponent("", "/")]
    elif not parts1[-1].seperator:
        parts1 = parts1[:-1]
    return parts1 + parts2


# Python's `urllib.parse.urljoin` sometimes normalizes consecutive '/'
# characters, which might break some URLs
def join_paths(base: str, path: str) -> str:
    """Join 2 HTTP paths, preserving the number of '/'s between components."""
    if path.startswith("/"):
        # path is already absolute
        return path
    base_parts = split_path_preserving_seperators(base)
    path_parts = split_path_preserving_seperators(path)
    all_parts = concat_path_components(base_parts, path_parts)
    return join_path_components(normalize_path(all_parts))


def relativize_html_http_url(
    url: str,
    parsed: urllib.parse.ParseResult,
    document_url: str,
    document_parsed: urllib.parse.ParseResult,
) -> str:
    """Relativize an HTML URL that has a host."""
    prefix = build_prefix(parsed)

    if parsed.path and parsed.path[0] != "/":
        path = prefix + "/" + parsed.path
    else:
        path = prefix + parsed.path

    return urllib.parse.urlunsplit(
        ("", "", path, parsed.query, parsed.fragment)
    )


def fix_relative_html_url(
    url: str,
    parsed: urllib.parse.ParseResult,
    document_url: str,
    document_parsed: urllib.parse.ParseResult,
) -> str:
    """Relativize an HTML URL that does not have a host."""
    prefix = build_prefix(document_parsed)

    if not document_parsed.path:
        base = "/"
    else:
        base = document_parsed.path
    path = join_paths(base, parsed.path)
    if path and path[0] != "/":
        path = prefix + "/" + path
    else:
        path = prefix + path

    return urllib.parse.urlunsplit(
        ("", "", path, parsed.query, parsed.fragment)
    )


def relativize_html_url(url: str, document_url: str) -> str:
    """Convert a URL from an HTML document to relative form.

    The document_url must be fully qualified. Especially, it must have a
    scheme.

    Arguments:
    url -- the URL to process
    document_url -- the URL of the HTML file

    Returns: the processed URL
    """
    document_parsed = urllib.parse.urlsplit(document_url.strip())
    stripped_url = url.lstrip().lower()
    if stripped_url.startswith("#"):  # just a fragment
        return url
    elif stripped_url.startswith("blob:"):
        url = url[5:]
    elif stripped_url.startswith("//"):
        url = document_parsed.scheme + ":" + url
    try:
        parsed = urllib.parse.urlsplit(url.strip())
    except ValueError:  # we failed to parse the URL
        return url
    if parsed.scheme.lower() in ["http", "https"]:
        return relativize_html_http_url(
            url, parsed, document_url, document_parsed
        )
    elif not parsed.scheme:
        return fix_relative_html_url(
            url, parsed, document_url, document_parsed
        )
    else:
        return url


class HTMLAttributeRewritter(ABC):
    """Base class of all attribute rewriters."""

    @abstractmethod
    def __init__(self, attr: str, value: str):
        """Create an HTMLAttributeRewritter.

        Arguments:
        attr -- The name of the attribute
        value -- The value of the attribute
        """
        pass

    @abstractmethod
    def decode(self) -> list[str]:
        """Return a list of URLs to rewrite.

        Returns: the list of URLs
        """
        pass

    @abstractmethod
    def encode(self, new_urls: list[str]) -> str:
        """Encode the original attribute value, using new URLs.

        Arguments:
        new_urls -- The list of URLs to use

        Returns: the new HTML attribute value
        """
        pass


class HTMLTagMatcher(ABC):
    """Base class of all HTML tag matchers."""

    @abstractmethod
    def matches(self, tag: Tag) -> bool:
        """Test weather a give tag matches this matcher.

        Arguments:
        tag -- the tag to test

        Returns: the result of the test
        """
        pass


class HTMLRewriteRule(NamedTuple):
    """Rule for rewriting a single HTML tag."""

    # The tag name
    tag_name: str
    # Extra matchers (e.g. on attribute names/values)
    match: HTMLTagMatcher
    # The rewrite rules
    rewrite: dict[str, type[HTMLAttributeRewritter]] = {}
    # Whether to remove this tag entirely
    remove: bool = False


class HTMLRewritter(NamedTuple):
    """List of rules to rewrite an HTML document."""

    rules: dict[str, list[HTMLRewriteRule]]

    @classmethod
    def compile(*rules: list[HTMLRewriteRule]):
        d: dict[str, list[HTMLRewriteRule]] = {}
        for rule in rules:
            if rule.tag_name not in d:
                d[rule.tag_name] = [rule]
            else:
                d[rule.tag_name].append(rule)


def relativize_html(text: str, url: str) -> str:
    """Normalize all URls in the HTML document text.

    This will handle embedded CSS and SVG data in the HTML file.

    Arguments:
    text -- The HTML document to process
    url -- The orignal URL the document was recieved from
    """
    soup = BeautifulSoup(text, "html.parser")
    for tag in soup.find_all():
        pass
    pass
