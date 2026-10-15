"""
URL Rewriting Code

This file contains code that parses HTML/CSS documents and normalizes all URLs
so the document
"""

import tinycss2
from bs4 import BeautifulSoup, Tag
import urllib.parse
from typing import Callable, NamedTuple
from abc import ABC, abstractmethod


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


def relativize_html_url(url: str, document_url: str) -> str:
    """Convert a URL from an HTML document to relative form.

    Arguments:
    url -- the URL to process
    document_url -- the URL of the HTML file

    Returns: the processed URL
    """
    pass


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
