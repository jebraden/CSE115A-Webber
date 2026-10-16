"""
URL Rewriting Code

This file contains code that parses HTML/CSS documents and normalizes all URLs.

The primary public functions are:
 - relativize_html -- Relativize an HTML file
 - relativize_stylesheet -- Relativize a standalone CSS file
"""

import tinycss2
from bs4 import BeautifulSoup, Tag
import urllib.parse
from typing import NamedTuple, Optional, Protocol, override, Iterator
from abc import ABC, abstractmethod
from itertools import islice, takewhile
import re
import base64
import binascii


class URLRewriter(ABC):
    """Rewrite URLs in HTML, CSS, etc. documents."""

    def __init__(self, document_url: str):
        """Construct a URLRewriter.

        Arguments:
        document_url -- the URL of the HTML document to process
        """
        self.document_url = document_url

    def parse_document_url(
        self, document_url: str
    ) -> urllib.parse.ParseResult:
        """Parse a document URL into parts.

        Arguments:
        document_url -- the document URL

        Returns: the parsed URL in the same format as `urllib.parse.urlsplit`
        """
        return urllib.parse.urlsplit(document_url.strip())

    @property
    def document_url(self) -> str:
        """The document's URL."""
        return self._document_url

    @document_url.setter
    def document_url(self, document_url: str):
        """Set the document's URL."""
        self._document_url = document_url
        self.document_parsed = self.parse_document_url(document_url)

    @abstractmethod
    def rewrite(self, url: str) -> str:
        """Rewrite a URL.

        Arguments:
        url -- the URL to rewrite

        Returns: the rewritten URL
        """
        pass

    def copy(self, document_url: Optional[str] = None) -> URLRewriter:
        """Copy this instance, optionally replacing the document_url.

        Arguments:
        document_url -- the new document URL to use

        Returns: the copy
        """
        return type(self)(
            document_url if document_url is not None else self.document_url
        )


class PathComponent(NamedTuple):
    file: str
    seperator: str


def _split_path_preserving_seperators(path: str) -> list[PathComponent]:
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


def _normalize_path(parts: list[PathComponent]) -> list[PathComponent]:
    """Remove '.' and '..' from an HTTP path."""
    out = []
    for i in range(len(parts)):
        part = parts[i]
        if part.file == "..":
            # just ignore if the path starts with ".."
            if out and out[-1].file:
                out.pop()
        elif part.file != ".":
            out.append(part)
    return out


def _join_path_components(parts: list[PathComponent]) -> str:
    """Join a list of PathComponents into a string path."""
    return "".join(map(lambda part: part.file + part.seperator, parts))


def _concat_path_components(
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
    """Resolve a path against a base, following HTTP URL conventions.

    If path is absolute, just return it unchanged. Consecutive '/' characters
    are preserved.

    Arguments:
    base -- the path to resolve against
    path -- the path to be resolved

    Returns: path resolved against base
    """
    if path.startswith("/"):
        # path is already absolute
        return path
    base_parts = _split_path_preserving_seperators(base)
    path_parts = _split_path_preserving_seperators(path)
    all_parts = _concat_path_components(base_parts, path_parts)
    return _join_path_components(_normalize_path(all_parts))


def _count_levels(parts: list[PathComponent]) -> int:
    """Count the number of '..'s to add to reach '/' from path.

    The path must be normal (not have any '..'s or '.'s in it).
    """
    if not parts:
        return 0
    count = len(parts)
    if not parts[0].file:
        count -= 1
    if len(parts) > 1 and not parts[-1].seperator:
        count -= 1
    return count


def _count_leading_upwards(parts: list[PathComponent]) -> int:
    if not parts:
        return 0
    start = 0 if parts[0].file else 1
    return len(
        list(takewhile(lambda c: c.file == "..", islice(parts, start, None)))
    )


class URLRelativizer(URLRewriter):
    """URLRewriter that relativizes URLs."""

    def _get_split_result_port(
        self,
        parsed: urllib.parse.ParseResult,
    ) -> Optional[int]:
        """Try to extract the port from a parsed URL.

        Return None if the port was not a number.
        """
        try:
            return parsed.port
        except ValueError:
            return None

    def _construct_netloc(self, username, password, hostname, port):
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

    def _normalize_netloc_port(self, parsed: urllib.parse.ParseResult) -> str:
        """Maybe remove a netloc port if it is redundant with the scheme."""
        scheme = parsed.scheme.lower()
        port = self._get_split_result_port(parsed)
        if (scheme == "http" and port == 80) or (
            scheme == "https" and port == 443
        ):
            return self._construct_netloc(
                parsed.username, parsed.password, parsed.hostname, None
            )
        else:
            return parsed.netloc

    def _build_prefix(self, parsed: urllib.parse.ParseResult) -> str:
        """Build a URL encoded path component from a URLs scheme and netloc."""
        netloc = self._normalize_netloc_port(parsed)
        scheme = parsed.scheme.lower()
        return urllib.parse.quote(scheme + "://" + netloc, safe="")

    def _relativize_html_hostful_url(
        self,
        url: str,
        parsed: urllib.parse.ParseResult,
    ) -> str:
        """Relativize an HTML URL that has a host."""
        # The extra +1 is for going into the directory containing hosts
        depth = self._document_depth + 1
        prefix = ("../" * depth) + self._build_prefix(parsed)

        path_parts = _split_path_preserving_seperators(parsed.path)
        norm_path = _join_path_components(_normalize_path(path_parts))
        if parsed.path and parsed.path[0] != "/":
            path = prefix + "/" + norm_path
        else:
            path = prefix + norm_path

        return urllib.parse.urlunsplit(
            ("", "", path, parsed.query, parsed.fragment)
        )

    def _relativize_html_hostless_url(
        self, url: str, parsed: urllib.parse.ParseResult
    ) -> str:
        """Relativize a URL without a host."""
        path_parts = _split_path_preserving_seperators(parsed.path)
        if parsed.path.startswith("/"):
            path_parts = path_parts[1:]
            leading_upwards = self._document_depth
        else:
            leading_upwards = min(
                self._document_depth, _count_leading_upwards(path_parts)
            )
        norm_path = _join_path_components(_normalize_path(path_parts))
        path = ("../" * leading_upwards) + norm_path
        return urllib.parse.urlunsplit(
            ("", "", path, parsed.query, parsed.fragment)
        )

    def _relativize_b64_data(
        self, url: str, content_type: str, data: str
    ) -> str:
        try:
            bin_data = base64.b64decode(data)
            data = bin_data.decode(errors="ignore")
        except binascii.Error:
            return url
        rel_data = relativize_html(data, self.document_url)
        rel_bin_data = rel_data.encode(errors="ignore")
        enc_data = base64.b64encode(rel_bin_data).decode(errors="ignore")
        return f"data:{content_type};base64,{enc_data}"

    def _relativize_data_url(self, url: str) -> str:
        """Relativize a \"data:\" URL."""
        match = re.match("^data:([^;]+)(;base64)?,(.*)$", url, re.DOTALL)
        if not match:
            return url
        content_type = match[1]
        if content_type not in ["text/html", "image/svg+xml"]:
            return url
        if match[2] is not None:
            return self._relativize_b64_data(url, content_type, match[3])
        rel_data = relativize_html(match[3], self.document_url)
        return f"data:{content_type},{rel_data}"

    @override
    def parse_document_url(
        self, document_url: str
    ) -> urllib.parse.ParseResult:
        url_parts = super().parse_document_url(document_url)
        path_parts = _split_path_preserving_seperators(url_parts.path)
        norm_parts = _normalize_path(path_parts)
        self._document_depth = _count_levels(norm_parts)
        return url_parts

    @override
    def rewrite(self, url: str) -> str:
        stripped_url = url.lstrip().lower()
        if stripped_url.startswith("#"):  # just a fragment
            return url
        elif stripped_url.startswith("blob:"):
            url = url[5:]
        elif stripped_url.startswith("//"):
            url = self.document_parsed.scheme + ":" + url
        try:
            parsed = urllib.parse.urlsplit(url.strip())
        except ValueError:  # we failed to parse the URL, return a safe value
            return ""
        scheme = parsed.scheme.lower()
        if scheme in ["http", "https"]:
            return self._relativize_html_hostful_url(url, parsed)
        elif scheme == "data":
            return self._relativize_data_url(url)
        elif not parsed.scheme:
            return self._relativize_html_hostless_url(url, parsed)
        else:
            return url


class HTMLAttributeRewriter(Protocol):
    """Protocol for rewriting HTML attributes."""

    def __call__(
        self,
        attr: str,
        value: str,
        rewrite_func: URLRewriter,
    ) -> str:
        """Rewrite a given HTML attribute.

        Arguments:
        attr -- the attribute's name
        value -- the attribute's value (to be rewritten)
        relativize_func -- the function to use to rewrite URLs

        Returns: the rewritten attribute value
        """
        pass


def identity_attribute_rewriter(
    attr: str,
    value: str,
    rewriter: URLRewriter,
) -> str:
    """HTMLAttributeRewriter that just rewrites the whole value."""
    return rewriter.rewrite(value)


def list_attribute_rewriter(
    attr: str,
    value: str,
    rewriter: URLRewriter,
) -> str:
    """HTMLAttributeRewriter that splits the value on spaces."""
    return " ".join(
        map(rewriter.rewrite, filter(bool, re.split(r"\s", value)))
    )


def srcset_attribute_rewriter(
    attr: str,
    value: str,
    rewriter: URLRewriter,
) -> str:
    """HTMLAttributeRewriter for srcset attributes."""
    urls = []
    sizes = []
    for entry in value.split(","):
        parts = list(filter(bool, re.split(r"\s", entry)))
        urls.append(parts[0])
        if len(parts) == 2:
            sizes.append(parts[1])
        else:
            sizes.append("")
    return ", ".join(map(" ".join, zip(map(rewriter.rewrite, urls), sizes)))


def srcdoc_attribute_rewriter(
    attr: str,
    value: str,
    rewriter: URLRewriter,
) -> str:
    """HTMLAttributeRewriter for srcdoc attributes."""
    return relativize_html(value, rewriter.document_url)


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


class HTMLAttributeValueTagMatcher(HTMLTagMatcher):
    """HTML Tag matcher that matches on attribute values."""

    def __init__(self, *args: list[tuple[str, str]]):
        """Construct the matcher.

        Arguments:
        args -- a list of tuples representing attributes and their values
        """
        self.attrs: dict[str, list[str]] = {}
        for attr, value in args:
            if attr in self.attrs:
                self.attrs[attr].append(value)
            else:
                self.attrs[attr] = [value]

    def matches(self, tag: Tag) -> bool:
        for attr, value in tag.attrs.items():
            if attr in self.attrs:
                if value in self.attrs[attr]:
                    return True
        return False


class HTMLRewriteRule(NamedTuple):
    """Rule for rewriting a single HTML tag."""

    # The tag name
    tag_name: str
    # Extra matchers (e.g. on attribute names/values)
    match: Optional[HTMLTagMatcher] = None
    # The rewrite rules
    rewriters: dict[str, HTMLAttributeRewriter] = {}
    # Whether to remove this tag entirely
    remove: bool = False

    def matches(self, tag: Tag) -> bool:
        """Test if a tag matches this rule.

        Arguments:
        tag -- the tag to test

        Returns: the result of the test
        """
        return not self.match or self.match.matches(tag)

    def rewrite(
        self,
        tag: Tag,
        url_rewriter: URLRewriter,
    ):
        """Destructively rewrite a tag according to this rule.

        Arguments:
        tag -- the tag to rewrite
        url_rewriter -- the URLRewriter to use to rewrite the tags
        """
        assert not self.remove or not self.rewriters
        if self.remove:
            tag.decompose()
        else:
            for attr, value in tag.attrs.items():
                if attr in self.rewriters:
                    new_value = self.rewriters[attr](attr, value, url_rewriter)
                    tag[attr] = new_value


class HTMLRewriter(NamedTuple):
    """List of rules to rewrite an HTML document."""

    rules: dict[str, list[HTMLRewriteRule]]

    def rewrite(self, tag: Tag, rewriter: URLRewriter) -> bool:
        """Destructively rewrite an HTML tag.

        Arguments:
        tag -- the tag to rewrite
        rewriter -- the rewriter to use

        Returns: whether the tag matched any rules
        """
        if tag.name in self.rules:
            for rule in self.rules[tag.name]:
                if rule.matches(tag):
                    rule.rewrite(tag, rewriter)
                    return True
        return False

    @classmethod
    def compile(cls, *rules: list[HTMLRewriteRule]) -> HTMLRewriter:
        """Compile a list of rewrite rules.

        The order of rules in this list matters.

        Arguments:
        rules -- the list of rules

        Returns: the compiled rewriter
        """
        d: dict[str, list[HTMLRewriteRule]] = {}
        for rule in rules:
            if rule.tag_name not in d:
                d[rule.tag_name] = [rule]
            else:
                d[rule.tag_name].append(rule)
        return HTMLRewriter(d)


REWRITER = HTMLRewriter.compile(
    # Elements to remove
    HTMLRewriteRule("base", remove=True),
    HTMLRewriteRule(
        "link",
        HTMLAttributeValueTagMatcher(
            ("rel", "prefetch"), ("rel", "dns-prefetch"), ("rel", "preconnect")
        ),
        remove=True,
    ),
    # Simple (non-recursive cases)
    # Link
    HTMLRewriteRule("link", rewriters={"href": identity_attribute_rewriter}),
    # Img and Map
    HTMLRewriteRule(
        "img",
        rewriters={
            "src": identity_attribute_rewriter,
            "srcset": srcset_attribute_rewriter,
        },
    ),
    HTMLRewriteRule("area", rewriters={"href": identity_attribute_rewriter}),
    # Forms
    HTMLRewriteRule("form", rewriters={"action": identity_attribute_rewriter}),
    HTMLRewriteRule(
        "input",
        rewriters={
            "src": identity_attribute_rewriter,
            "formaction": identity_attribute_rewriter,
            "srcset": srcset_attribute_rewriter,
        },
    ),
    HTMLRewriteRule(
        "button", rewriters={"formaction": identity_attribute_rewriter}
    ),
    # Video and Picture
    HTMLRewriteRule(
        "video",
        rewriters={
            "poster": identity_attribute_rewriter,
            "src": identity_attribute_rewriter,
        },
    ),
    HTMLRewriteRule(
        "source",
        rewriters={
            "src": identity_attribute_rewriter,
            "srcset": srcset_attribute_rewriter,
        },
    ),
    HTMLRewriteRule("track", rewriters={"src": identity_attribute_rewriter}),
    # Links
    HTMLRewriteRule(
        "a",
        rewriters={
            "href": identity_attribute_rewriter,
            "ping": identity_attribute_rewriter,
        },
    ),
    # Script
    HTMLRewriteRule("script", rewriters={"src": identity_attribute_rewriter}),
    # Embed and Object
    HTMLRewriteRule(
        "embed",
        rewriters={
            "src": identity_attribute_rewriter,
            "codebase": identity_attribute_rewriter,
            "archive": identity_attribute_rewriter,
        },
    ),
    HTMLRewriteRule(
        "object",
        rewriters={
            "data": identity_attribute_rewriter,
            "codebase": identity_attribute_rewriter,
            "archive": list_attribute_rewriter,
        },
    ),
    # Iframe
    HTMLRewriteRule(
        "iframe",
        rewriters={
            "src": identity_attribute_rewriter,
            "srcdoc": srcdoc_attribute_rewriter,
        },
    ),
    # Svg
    HTMLRewriteRule(
        "image",
        rewriters={
            "href": identity_attribute_rewriter,
            "xlink:href": identity_attribute_rewriter,
        },
    ),
    HTMLRewriteRule(
        "use",
        rewriters={
            "href": identity_attribute_rewriter,
            "xlink:href": identity_attribute_rewriter,
        },
    ),
    HTMLRewriteRule(
        "pattern", rewriters={"href": identity_attribute_rewriter}
    ),
    HTMLRewriteRule(
        "radialgradient", rewriters={"href": identity_attribute_rewriter}
    ),
    # svg link handled above
)


def relativize_html(text: str, url: str) -> str:
    """Normalize all URls in an HTML.

    This will handle embedded CSS and SVG data in the HTML file.

    Arguments:
    text -- the HTML document to process
    url -- the orignal URL the document was recieved from

    Return: the relativized text
    """
    soup = BeautifulSoup(text, "html.parser", multi_valued_attributes=False)
    rewriter = URLRelativizer(url)
    for tag in soup.find_all():
        REWRITER.rewrite(tag, rewriter)
        if not tag.decomposed and "style" in tag.attrs:
            tag["style"] = relativize_css_rule_list(tag["style"], url)
    for tag in soup.find_all("style"):
        tag.string.replace_with(relativize_stylesheet(tag.string, url))
    return str(soup)


def _find_all_css_urls(
    ast: list[tinycss2.ast.QualifiedRule],
) -> Iterator[tinycss2.ast.URLToken | tinycss2.ast.FunctionBlock]:
    """Find all CSS `url` function calls in an ast.

    Arguments:
    ast -- list of CSS AST nodes

    Returns: an iterator that will yield every `url` function call
    """

    def is_valid_url_node(fb: tinycss2.ast.FunctionBlock) -> bool:
        args = list(
            filter(
                lambda n: not isinstance(n, tinycss2.ast.WhitespaceToken),
                fb.arguments,
            )
        )
        return (
            len(args) == 1
            and isinstance(args[0], tinycss2.ast.StringToken)
            and fb.lower_name == "url"
        )

    to_scan: list[tinycss2.ast.Node] = ast.copy()
    while to_scan:
        cur = to_scan.pop()
        if isinstance(cur, tinycss2.ast.QualifiedRule):
            to_scan.extend(cur.content or [])
        if isinstance(cur, tinycss2.ast.Declaration):
            to_scan.extend(cur.value or [])
        elif isinstance(cur, tinycss2.ast.CurlyBracketsBlock):
            to_scan.extend(cur.content or [])
        elif isinstance(cur, tinycss2.ast.AtKeywordToken):
            to_scan.extend(cur.prelude or [])
            to_scan.extend(cur.content or [])
        elif isinstance(cur, tinycss2.ast.AtRule):
            to_scan.extend(cur.prelude or [])
            to_scan.extend(cur.content or [])
        elif isinstance(cur, tinycss2.ast.URLToken):
            yield cur
        elif isinstance(cur, tinycss2.ast.FunctionBlock) and is_valid_url_node(
            cur
        ):
            yield cur


def _rewrite_css_token_url(
    token: tinycss2.ast.URLToken | tinycss2.ast.FunctionBlock,
    rewriter: URLRewriter,
):
    """Destructively rewrite a CSS URL token's URL."""
    if isinstance(token, tinycss2.ast.URLToken):
        url = rewriter.rewrite(token.value)
        token.value = url
        token.representation = f"url({tinycss2.serializer.serialize_url(url)})"
    elif isinstance(token, tinycss2.ast.FunctionBlock):
        args = list(
            filter(
                lambda n: not isinstance(n, tinycss2.ast.WhitespaceToken),
                token.arguments,
            )
        )
        str_tok: tinycss2.ast.StringToken = args[0]
        url = rewriter.rewrite(str_tok.value)
        str_tok.value = url
        str_tok.representation = (
            f'"{tinycss2.serializer.serialize_string_value(url)}"'
        )


def _relativize_css_ast(ast: list[tinycss2.ast.Node], url: str) -> str:
    """Relativize a CSS AST."""
    rewriter = URLRelativizer(url)
    for token in _find_all_css_urls(ast):
        _rewrite_css_token_url(token, rewriter)
    try:
        return tinycss2.serializer.serialize(ast)
    except TypeError:
        return ""  # Safe value


def relativize_css_rule_list(text: str, url: str) -> str:
    """Relativize all URLs in a CSS fragment (e.g. an HTML style attribute).

    Arguments:
    text -- the CSS to process
    url -- the URL of the containing file

    Returns: the processed CSS as a `str`
    """
    ast = tinycss2.parse_blocks_contents(text)
    return _relativize_css_ast(ast, url)


def relativize_stylesheet(text: str | bytes, url: str) -> str:
    """Relativize all URLs in a CSS document.

    Arguments:
    text -- the CSS to process, as `bytes` or `str`
    url -- the URL of the CSS file

    Returns: the processed CSS as a `str`
    """
    if isinstance(text, str):
        ast = tinycss2.parse_stylesheet(text)
    elif isinstance(text, bytes):
        # returns a tuple of (ast, encoding)
        ast = tinycss2.parse_stylesheet_bytes(text)[0]
    else:
        raise TypeError("CSS text must be str or bytes")
    return _relativize_css_ast(ast, url)
