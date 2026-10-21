from src.urlreplace import (
    URLRelativizer,
    join_paths,
    relativize_html,
    relativize_stylesheet,
    relativize_css_rule_list,
)
import pytest
import base64
from bs4 import BeautifulSoup
import os


class TestJoinPaths:
    def test_absolute_path(self):
        """If path starts with /, return it unchanged."""
        assert join_paths("/a/b", "/c/d") == "/c/d"
        assert join_paths("/a/b", "/") == "/"
        assert join_paths("", "/c/d") == "/c/d"

    def test_basic_join_with_trailing_slash(self):
        """Join paths when base ends with /."""
        assert join_paths("/a/b/", "c/d") == "/a/b/c/d"
        assert join_paths("/a/b/", "c") == "/a/b/c"
        assert join_paths("/", "a") == "/a"

    def test_basic_join_without_trailing_slash(self):
        """When base doesn't end with /, remove last component before joining."""
        assert join_paths("/a/b", "c/d") == "/a/c/d"
        assert join_paths("/a/b", "c") == "/a/c"
        assert join_paths("/a", "b") == "/b"

    def test_consecutive_slashes_preserved(self):
        """Consecutive slashes should be preserved."""
        assert join_paths("/a//b/", "c") == "/a//b/c"
        assert join_paths("/a/b", "//c") == "//c"
        assert join_paths("/a/", "b//c") == "/a/b//c"
        assert join_paths("/a//", "b") == "/a//b"

    def test_dot_components(self):
        """'.' components should be removed."""
        assert join_paths("/a/", "./b") == "/a/b"
        assert join_paths("/a/", ".") == "/a/"
        assert join_paths("/a/", "b/./c") == "/a/b/c"
        assert join_paths("/a/", "./b/./c") == "/a/b/c"

    def test_dotdot_components(self):
        """'..' components should remove previous component."""
        assert join_paths("/a/b/", "../c") == "/a/c"
        assert join_paths("/a/b/", "../../c") == "/c"
        assert join_paths("/a/b/c/", "../../d") == "/a/d"
        assert join_paths("/a/b/", "../b/../../c") == "/c"

    def test_dotdot_at_root_preserves_leading_slash(self):
        """'..' at root should preserve leading slash."""
        assert join_paths("/a/", "../b") == "/b"
        assert join_paths("/", "../b") == "/b"
        assert join_paths("/a/", "../../b") == "/b"
        assert join_paths("//a", "../b/b") == "//b/b"
        assert join_paths("/a", "../b") == "/b"

    def test_multiple_dotdot_at_root(self):
        """Multiple '..' at root should still preserve leading slash."""
        assert join_paths("/a/", "../../../b") == "/b"
        assert join_paths("/", "../../b") == "/b"
        assert join_paths("//a", "../../b") == "//b"

    def test_mixed_dots_and_slashes(self):
        """Complex paths with dots and consecutive slashes."""
        assert join_paths("/a//b/", "../c//d") == "/a//c//d"
        assert join_paths("/a/b/", "./../c") == "/a/c"
        assert join_paths("/a/b/", ".././c") == "/a/c"

    def test_empty_path(self):
        """Empty path should return base directory with trailing slash."""
        assert join_paths("/a/", "") == "/a/"
        assert join_paths("/a", "") == "/"

    def test_empty_base(self):
        """Empty base should be treated as root."""
        assert join_paths("", "a") == "/a"
        assert join_paths("", "/a") == "/a"
        assert join_paths("", "") == "/"

    def test_root_path(self):
        """Root path handling."""
        assert join_paths("/", "a") == "/a"
        assert join_paths("/", "/a") == "/a"
        assert join_paths("/", "") == "/"

    def test_multiple_dots(self):
        """Multiple dots in filename should be preserved."""
        assert join_paths("/a/", "...") == "/a/..."
        assert join_paths("/a/", "file...txt") == "/a/file...txt"
        assert join_paths("/a/", "b.../c") == "/a/b.../c"

    def test_complex_real_world(self):
        """Complex real-world path scenarios."""
        # Directory navigation
        assert (
            join_paths("/home/user/docs/", "../images/photo.jpg")
            == "/home/user/images/photo.jpg"
        )

        # Deep nesting
        assert join_paths("/a/b/c/d/", "../../../e/f") == "/a/e/f"

        # Mixed with consecutive slashes
        assert join_paths("/a//b/c/", "../d//e") == "/a//b/d//e"

        # Trailing dots
        assert join_paths("/a/b/", "c/.") == "/a/b/c/"

    def test_single_component(self):
        """Single component paths."""
        assert join_paths("/a/", "b") == "/a/b"
        assert join_paths("/a", "b") == "/b"
        assert join_paths("/", "a") == "/a"

    def test_multiple_consecutive_dots(self):
        """Multiple consecutive .. components."""
        assert join_paths("/a/b/c/", "../../d") == "/a/d"
        assert join_paths("/a/b/c/", "../../../d") == "/d"
        assert (
            join_paths("/a/b/c/", "../../../../d") == "/d"
        )  # Can't go above root


class TestURLRelativizer:
    """Tests for URLRelativizer URL rewriting.

    The storage format is:
    snapshots/SNAPSHOT_ID/URL_ENCODED_HOST/path/to/file

    So from snapshots/SNAPSHOT_ID/www.example.com/page/index.html:
    - Link to http://www.other.com/style.css → ../../http%3A%2F%2Fwww.other.com/style.css
    - Link to /css/main.css → ../css/main.css
    - Link to ./img/logo.png → img/logo.png
    """

    def assert_urls(self, document_url: str, urls: list[tuple[str, str]]):
        rewriter = URLRelativizer(document_url)
        for original, output in urls:
            assert rewriter.rewrite(original) == output

    def test_absolute_urls(self):
        """Absolute URLs resolve to encoded host prefix + path."""
        self.assert_urls(
            "http://www.example.com/",
            [
                ("http://example.com/", "../http%3A%2F%2Fexample.com/"),
                (
                    "https://www.example.com/",
                    "../https%3A%2F%2Fwww.example.com/",
                ),
                (
                    "https://www.example.com/a/b.html",
                    "../https%3A%2F%2Fwww.example.com/a/b.html",
                ),
                (
                    "https://www.example.com/a/b.html?param1=val&param2=val#fragment",
                    "../https%3A%2F%2Fwww.example.com/a/b.html?param1=val&param2=val#fragment",
                ),
            ],
        )

    def test_protocol_relative_urls(self):
        """Protocol-relative URLs resolve against document's protocol."""
        self.assert_urls(
            "http://www.example.com/",
            [
                ("//example.com/path", "../http%3A%2F%2Fexample.com/path"),
                (
                    "//example.com:8080/path",
                    "../http%3A%2F%2Fexample.com%3A8080/path",
                ),
                (
                    "//cdn.example.com/script.js",
                    "../http%3A%2F%2Fcdn.example.com/script.js",
                ),
                (
                    "//user:pass@example.com/file",
                    "../http%3A%2F%2Fuser%3Apass%40example.com/file",
                ),
            ],
        )
        self.assert_urls(
            "https://www.example.com/",
            [
                ("//example.com/path", "../https%3A%2F%2Fexample.com/path"),
                (
                    "//example.com:8080/path",
                    "../https%3A%2F%2Fexample.com%3A8080/path",
                ),
            ],
        )

    def test_root_relative_urls(self):
        """Root-relative URLs resolve against document's host."""
        self.assert_urls(
            "http://www.example.com/",
            [
                ("/path/file", "path/file"),
                ("/", ""),
                ("/css/main.css", "css/main.css"),
                (
                    "/api/data?query=1",
                    "api/data?query=1",
                ),
            ],
        )

    def test_document_relative_urls(self):
        """Document-relative URLs resolve against document's path."""
        self.assert_urls(
            "http://www.example.com/page/",
            [
                ("path/file", "path/file"),
                ("./path/file", "path/file"),
                ("../path/file", "../path/file"),
                ("../../path/file", "../path/file"),
                (
                    "img/logo.png",
                    "img/logo.png",
                ),
            ],
        )

    def test_fragment_only_urls(self):
        """Fragment-only URLs should be preserved."""
        self.assert_urls(
            "http://www.example.com/",
            [
                ("#section", "#section"),
                ("#", "#"),
                ("#fragment-id", "#fragment-id"),
                ("#top", "#top"),
            ],
        )

    def test_data_uri_urls(self):
        """Data URIs are self-contained and should be preserved.

        Embedded SVG and HTML URLs are handled below.
        """
        self.assert_urls(
            "http://www.example.com/",
            [
                (
                    "data:image/png;base64,iVBORw0KGgo...",
                    "data:image/png;base64,iVBORw0KGgo...",
                ),
                (
                    "data:text/plain;charset=UTF-8,Hello%20World",
                    "data:text/plain;charset=UTF-8,Hello%20World",
                ),
            ],
        )

    def test_blob_urls(self):
        """Blob URLs are temporary, but will be captured by playwright."""
        self.assert_urls(
            "http://www.example.com/",
            [
                (
                    "blob:http://example.com/uuid-1234",
                    "../http%3A%2F%2Fexample.com/uuid-1234",
                ),
                (
                    "blob:https://example.com/uuid-5678",
                    "../https%3A%2F%2Fexample.com/uuid-5678",
                ),
                (
                    "blob:http://localhost/8f34f9d6-385e-483b-9eff-fea4b9e9b9b6",
                    "../http%3A%2F%2Flocalhost/8f34f9d6-385e-483b-9eff-fea4b9e9b9b6",
                ),
            ],
        )

    def test_special_schemes(self):
        """Special schemes should be preserved."""
        self.assert_urls(
            "http://www.example.com/",
            [
                ("mailto:user@example.com", "mailto:user@example.com"),
                (
                    "mailto:user@example.com?subject=Hello",
                    "mailto:user@example.com?subject=Hello",
                ),
                ("tel:+1234567890", "tel:+1234567890"),
                ("tel:1234567890", "tel:1234567890"),
                ("sms:+1234567890", "sms:+1234567890"),
                ("sms:+1234567890?&body=hi", "sms:+1234567890?&body=hi"),
                ("javascript:void(0)", "javascript:void(0)"),
                ("javascript:alert('hi')", "javascript:alert('hi')"),
                ("javascript:window.location", "javascript:window.location"),
                ("about:blank", "about:blank"),
                ("about:srcdoc", "about:srcdoc"),
            ],
        )

    def test_query_strings(self):
        """Query strings should be preserved."""
        self.assert_urls(
            "http://www.example.com/",
            [
                ("?param=value", "?param=value"),
                ("path?query=1", "path?query=1"),
                (
                    "path?param1=val&param2=val",
                    "path?param1=val&param2=val",
                ),
                (
                    "https://example.com/api?format=json&type=html",
                    "../https%3A%2F%2Fexample.com/api?format=json&type=html",
                ),
            ],
        )

    def test_encoded_urls(self):
        """URL-encoded URLs should be properly handled."""
        self.assert_urls(
            "http://www.example.com/",
            [
                (
                    "http%3A%2F%2Fexample.com%2Fpath",
                    "http%3A%2F%2Fexample.com%2Fpath",
                ),
            ],
        )

    def test_ports(self):
        """Ports should be encoded in host prefix."""
        self.assert_urls(
            "http://www.example.com/",
            [
                (
                    "http://example.com:8080/path",
                    "../http%3A%2F%2Fexample.com%3A8080/path",
                ),
                (
                    "https://example.com:443/path",
                    "../https%3A%2F%2Fexample.com/path",
                ),
                (
                    "https://example.com:444/path",
                    "../https%3A%2F%2Fexample.com%3A444/path",
                ),
                (
                    "//example.com:8080/path",
                    "../http%3A%2F%2Fexample.com%3A8080/path",
                ),
                (
                    "//example.com:80/path",
                    "../http%3A%2F%2Fexample.com/path",
                ),
            ],
        )

    def test_credentials(self):
        """Credentials should be encoded in host prefix."""
        self.assert_urls(
            "http://www.example.com/",
            [
                (
                    "http://user:pass@example.com/",
                    "../http%3A%2F%2Fuser%3Apass%40example.com/",
                ),
                (
                    "https://user@example.com/",
                    "../https%3A%2F%2Fuser%40example.com/",
                ),
                (
                    "//user:pass@example.com/file",
                    "../http%3A%2F%2Fuser%3Apass%40example.com/file",
                ),
            ],
        )

    def test_fragments_with_url(self):
        """Fragments should be preserved when attached to URLs."""
        self.assert_urls(
            "http://www.example.com/",
            [
                ("path#section", "path#section"),
                (
                    "https://example.com/page#fragment",
                    "../https%3A%2F%2Fexample.com/page#fragment",
                ),
                (
                    "https://example.com/page?query=1#frag",
                    "../https%3A%2F%2Fexample.com/page?query=1#frag",
                ),
                ("#fragment", "#fragment"),  # Fragment only
            ],
        )

    def test_empty_and_whitespace(self):
        """Whitespace should be removed."""
        self.assert_urls(
            "http://www.example.com/a/",
            [
                ("", ""),
                ("   ", ""),
                ("\t\n", ""),
                ("  http://example.com  ", "../../http%3A%2F%2Fexample.com"),
            ],
        )
        self.assert_urls(
            "http://www.example.com/a",
            [
                ("", ""),
                ("   ", ""),
                ("\t\n", ""),
                ("  http://example.com  ", "../http%3A%2F%2Fexample.com"),
            ],
        )

    def test_complex_urls(self):
        """Complex URLs with multiple components."""
        self.assert_urls(
            "http://www.example.com/",
            [
                (
                    "https://user:pass@example.com:8080/path?query=1#frag",
                    "../https%3A%2F%2Fuser%3Apass%40example.com%3A8080/path?query=1#frag",
                ),
                (
                    "//user:pass@example.com:8080/path",
                    "../http%3A%2F%2Fuser%3Apass%40example.com%3A8080/path",
                ),
                (
                    "https://example.com/path/to/file?param1=val&param2=val#section",
                    "../https%3A%2F%2Fexample.com/path/to/file?param1=val&param2=val#section",
                ),
            ],
        )

    def test_relative_resolution(self):
        """Test relative URL resolution against different document paths."""
        self.assert_urls(
            "http://www.example.com/a/b/c.html",
            [
                ("d/e.png", "d/e.png"),
                ("../d/e.png", "../d/e.png"),
                ("../../d/e.png", "../../d/e.png"),
                ("./d/e.png", "d/e.png"),
            ],
        )
        self.assert_urls(
            "http://www.example.com/a/b/c/",
            [
                ("d/e.png", "d/e.png"),
                ("../d/e.png", "../d/e.png"),
                ("../../d/e.png", "../../d/e.png"),
                ("./d/e.png", "d/e.png"),
            ],
        )

    def test_mixed_case(self):
        """URLs should preserve case (except the scheme)."""
        self.assert_urls(
            "http://www.example.com/",
            [
                (
                    "HTTP://EXAMPLE.COM/PATH",
                    "../http%3A%2F%2FEXAMPLE.COM/PATH",
                ),
                (
                    "https://Example.Com/Path",
                    "../https%3A%2F%2FExample.Com/Path",
                ),
            ],
        )

    def test_unicode(self):
        """Unicode URLs should be handled."""
        self.assert_urls(
            "http://www.example.com/",
            [
                (
                    "https://example.com/文件",
                    "../https%3A%2F%2Fexample.com/文件",
                ),
                (
                    "https://example.com/файл",
                    "../https%3A%2F%2Fexample.com/файл",
                ),
            ],
        )

    def test_depth_calculation(self):
        """Test that depth is correctly calculated for different document paths."""
        # Document at root - depth should be 0
        rewriter = URLRelativizer("http://www.example.com/index.html")
        assert rewriter._document_depth == 0

        # Document in one directory - depth should be 1
        rewriter = URLRelativizer("http://www.example.com/page/index.html")
        assert rewriter._document_depth == 1

        # Document in nested directories - depth should be 3
        rewriter = URLRelativizer("http://www.example.com/a/b/c/index.html")
        assert rewriter._document_depth == 3

    def test_hostful_urls_use_depth(self):
        """Test that hostful URLs use correct depth."""
        # At root, use 1 '../' to get to snapshot root, then encoded host
        rewriter = URLRelativizer("http://www.example.com/index.html")
        result = rewriter.rewrite("http://other.com/file.css")
        assert result == "../http%3A%2F%2Fother.com/file.css"

        # At depth 1, use 2 '../'s
        rewriter = URLRelativizer("http://www.example.com/page/index.html")
        result = rewriter.rewrite("http://other.com/file.css")
        assert result == "../../http%3A%2F%2Fother.com/file.css"

        # At depth 2, use 3 '../'s
        rewriter = URLRelativizer("http://www.example.com/a/b/index.html")
        result = rewriter.rewrite("http://other.com/file.css")
        assert result == "../../../http%3A%2F%2Fother.com/file.css"

    def test_hostless_urls_use_depth(self):
        """Test that hostless URLs use correct depth for root-relative."""
        # At depth 1, root-relative should use 1 '../' to go up to host dir
        rewriter = URLRelativizer("http://www.example.com/page/index.html")
        result = rewriter.rewrite("/css/main.css")
        assert result == "../css/main.css"

        # At depth 2
        rewriter = URLRelativizer("http://www.example.com/a/b/index.html")
        result = rewriter.rewrite("/css/main.css")
        assert result == "../../css/main.css"


class TestPathTraversalSafety:
    """Security tests to ensure URLs cannot escape the snapshot directory.

    The storage format is:
    snapshots/SNAPSHOT_ID/URL_ENCODED_HOST/path/to/file

    We need to ensure that even with malicious input containing many '..',
    the relativizer output cannot navigate above the snapshot root.
    """

    def test_hostful_url_cannot_escape_snapshot(self):
        """Hostful URLs should always use exactly depth+1 levels of '../'.

        Regardless of how many '..' are in the input path, the output for
        hostful URLs should always navigate to the snapshot root and then
        into the encoded host directory.
        """
        # Document at depth 1 (e.g., /page/index.html)
        rewriter = URLRelativizer("http://www.example.com/page/index.html")

        # Normal URL - should use 2 levels of ../ (depth + 1)
        result = rewriter.rewrite("http://other.com/file.txt")
        assert result.startswith("../../")
        assert not result.startswith("../../../")

        # Malicious URL with 100 levels of .. in path
        malicious = "http://other.com/" + "../" * 100 + "etc/passwd"
        result = rewriter.rewrite(malicious)

        # Should still use exactly 2 levels of ../ (depth + 1)
        # The path is normalized, so all '..' are removed
        assert result.startswith("../../")
        assert not result.startswith("../../../")

        # The encoded host should be present
        assert "other.com" in result

        # The path should be normalized (no ..)
        path_part = result.split("other.com")[-1]
        assert ".." not in path_part

    def test_hostless_absolute_cannot_escape(self):
        """Absolute hostless URLs should use at most depth levels of '../'.

        A URL like '/../../file' resolves against the host root, so from a
        document at depth 1, it should only use 1 level of ../.
        """
        rewriter = URLRelativizer("http://www.example.com/page/index.html")

        # Absolute URL with many ..
        result = rewriter.rewrite("/" + "../" * 50 + "file.txt")

        # Should use exactly 1 level of ../ (the document depth)
        # because it resolves against the host root
        assert result.startswith("../")
        assert not result.startswith("../../")

    def test_hostless_relative_cannot_escape(self):
        """Relative hostless URLs should be bounded by document depth.

        A URL like '../../../file' from a document at depth 1 should not
        create a path that escapes above the snapshot directory.
        """
        rewriter = URLRelativizer("http://www.example.com/page/index.html")

        # Relative URL with many ..
        result = rewriter.rewrite("../" * 50 + "file.txt")

        # Should use at most 1 level of ../ (document depth)
        assert result.startswith("../")
        assert not result.startswith("../../")

        # The path should be normalized
        assert result.endswith("file.txt")

    def test_deep_document_cannot_escape(self):
        """Even with deep document paths, output is bounded.

        From a deep path like /a/b/c/index.html (depth 3), URLs should
        still be properly bounded.
        """
        rewriter = URLRelativizer("http://www.example.com/a/b/c/index.html")

        # Hostful - should use exactly 4 levels of ../ (depth + 1)
        result = rewriter.rewrite("http://other.com/file.txt")
        assert result.startswith("../../../../")
        assert not result.startswith("../../../../../")

        # Hostless absolute - should use exactly 3 levels of ../
        result = rewriter.rewrite("/" + "../" * 100 + "file.txt")
        assert result.startswith("../../../")
        assert not result.startswith("../../../../")

        # Hostless relative - should use at most 3 levels of ../
        result = rewriter.rewrite("../" * 100 + "file.txt")
        assert result.startswith("../../../")
        assert not result.startswith("../../../../")

    def test_very_deep_document_cannot_escape(self):
        """Test some very deep bad URLs."""

        # Document at various depths
        test_cases = [
            ("http://www.example.com/index.html", 0),
            ("http://www.example.com/page/index.html", 1),
            ("http://www.example.com/a/b/index.html", 2),
            ("http://www.example.com/a/b/", 2),
        ]

        for doc_url, depth in test_cases:
            rewriter = URLRelativizer(doc_url)

            # Test malicious URLs (second value is hostfulness)
            malicious_urls = [
                ("http://evil.com/" + "../" * 100 + "secret.txt", True),
                ("/" + "../" * 100 + "secret.txt", False),
                ("../" * 100 + "secret.txt", False),
                ("/" + "../" * 100 + "/secret.txt", False),
            ]

            for url, hostful in malicious_urls:
                result = rewriter.rewrite(url)

                # Count the ../ levels
                levels_up = 0
                temp = result
                while temp.startswith("../"):
                    levels_up += 1
                    temp = temp[3:]

                assert levels_up == depth + hostful


class TestRelativizeHTML:
    """Tests for HTML relativization."""

    def test_anchor_links(self):
        """Test href rewriting in anchor tags."""
        html = '<a href="http://example.com/page">Link</a>'
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/page" in result

    def test_image_sources(self):
        """Test src rewriting in img tags."""
        html = '<img src="http://example.com/image.png">'
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/image.png" in result

    def test_script_sources(self):
        """Test src rewriting in script tags."""
        html = '<script src="http://example.com/script.js"></script>'
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/script.js" in result

    def test_link_stylesheets(self):
        """Test href rewriting in link tags."""
        html = '<link rel="stylesheet" href="http://example.com/style.css">'
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/style.css" in result

    def test_srcset_attribute(self):
        """Test srcset rewriting with multiple URLs."""
        html = '<img srcset="http://example.com/a.png 1x, http://example.com/b.png 2x">'
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/a.png" in result
        assert "http%3A%2F%2Fexample.com/b.png" in result
        assert "1x" in result
        assert "2x" in result

    def test_remove_base_tag(self):
        """Test that base tags are removed."""
        html = '<base href="http://example.com/">'
        result = relativize_html(html, "http://www.example.com/")
        assert "<base" not in result

    def test_remove_prefetch_links(self):
        """Test that prefetch/preconnect links are removed."""
        html = '<link rel="prefetch" href="http://example.com/">'
        result = relativize_html(html, "http://www.example.com/")
        assert "prefetch" not in result

        html = '<link rel="dns-prefetch" href="http://example.com/">'
        result = relativize_html(html, "http://www.example.com/")
        assert "dns-prefetch" not in result

        html = '<link rel="preconnect" href="http://example.com/">'
        result = relativize_html(html, "http://www.example.com/")
        assert "preconnect" not in result

    def test_preserve_normal_links(self):
        """Test that normal stylesheet links are preserved."""
        html = '<link rel="stylesheet" href="http://example.com/style.css">'
        result = relativize_html(html, "http://www.example.com/")
        assert "stylesheet" in result
        assert "http%3A%2F%2Fexample.com/style.css" in result

    def test_form_actions(self):
        """Test form action rewriting."""
        html = '<form action="http://example.com/submit">'
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/submit" in result

    def test_video_sources(self):
        """Test video src and poster rewriting."""
        html = '<video src="http://example.com/video.mp4" poster="http://example.com/poster.jpg">'
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/video.mp4" in result
        assert "http%3A%2F%2Fexample.com/poster.jpg" in result

    def test_iframe_sources(self):
        """Test iframe src rewriting."""
        html = '<iframe src="http://example.com/frame.html">'
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/frame.html" in result

    def test_svg_images(self):
        """Test SVG image href rewriting."""
        html = '<image href="http://example.com/image.png">'
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/image.png" in result

    def test_mixed_content(self):
        """Test relativization of mixed content."""
        html = """
        <html>
        <head>
            <base href="http://example.com/">
            <link rel="stylesheet" href="/style.css">
            <link rel="prefetch" href="http://prefetch.com/page">
        </head>
        <body>
            <a href="http://example.com/page">Link</a>
            <img src="http://example.com/img.png">
            <script src="http://example.com/app.js"></script>
        </body>
        </html>
        """
        result = relativize_html(html, "http://www.example.com/")

        # Base tag removed
        assert "<base" not in result
        # Prefetch removed
        assert "prefetch" not in result
        # Regular links rewritten
        assert "http%3A%2F%2Fexample.com" in result
        # Root-relative rewritten
        assert "../style.css" in result or "style.css" in result


class TestRelativizeCSS:
    """Tests for CSS URL relativization."""

    def test_url_function_absolute(self):
        """Test absolute URLs in url() functions."""
        css = "background: url(http://example.com/bg.png);"
        result = relativize_css_rule_list(css, "http://www.example.com/page/")
        assert "http%3A%2F%2Fexample.com/bg.png" in result
        assert "http://example.com" not in result

    def test_url_function_root_relative(self):
        """Test root-relative URLs in url() functions."""
        css = "background: url(/css/bg.png);"
        result = relativize_css_rule_list(css, "http://www.example.com/page/")
        assert "css/bg.png" in result or "../css/bg.png" in result

    def test_url_function_relative(self):
        """Test document-relative URLs in url() functions."""
        css = "background: url(./images/bg.png);"
        result = relativize_css_rule_list(css, "http://www.example.com/page/")
        assert "images/bg.png" in result

    def test_url_function_parent(self):
        """Test parent-relative URLs in url() functions."""
        css = "background: url(../assets/bg.png);"
        result = relativize_css_rule_list(css, "http://www.example.com/page/")
        assert "assets/bg.png" in result or "../assets/bg.png" in result

    def test_multiple_urls(self):
        """Test CSS with multiple url() functions."""
        css = """
        .first { background: url(http://example.com/a.png); }
        .second { background: url(http://example.com/b.png); }
        """
        result = relativize_stylesheet(css, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/a.png" in result
        assert "http%3A%2F%2Fexample.com/b.png" in result

    def test_quoted_urls(self):
        """Test URLs with quotes in url() functions."""
        css = """
        .single { background: url('http://example.com/a.png'); }
        .double { background: url("http://example.com/b.png"); }
        """
        result = relativize_stylesheet(css, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/a.png" in result
        assert "http%3A%2F%2Fexample.com/b.png" in result

    def test_data_uri_preserved(self):
        """Test that data URIs are preserved unchanged."""
        css = "background: url(data:image/png;base64,iVBORw0KGgo);"
        result = relativize_css_rule_list(css, "http://www.example.com/")
        assert "data:image/png;base64,iVBORw0KGgo" in result

    def test_fragment_preserved(self):
        """Test that fragments are preserved."""
        css = "background: url(http://example.com/bg.png#section);"
        result = relativize_css_rule_list(css, "http://www.example.com/")
        assert "#section" in result

    def test_query_string_preserved(self):
        """Test that query strings are preserved."""
        css = "background: url(http://example.com/bg.png?v=1);"
        result = relativize_css_rule_list(css, "http://www.example.com/")
        assert "v=1" in result

    def test_import_statement(self):
        """Test @import URL rewriting."""
        css = "@import url(http://example.com/import.css);"
        result = relativize_stylesheet(css, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/import.css" in result

    def test_multiple_imports(self):
        """Test multiple @import statements."""
        css = """
        @import url(http://example.com/one.css);
        @import url(http://example.com/two.css);
        """
        result = relativize_stylesheet(css, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/one.css" in result
        assert "http%3A%2F%2Fexample.com/two.css" in result

    def test_url_with_spaces(self):
        """Test URLs with spaces (encoded)."""
        css = "background: url(http://example.com/path%20with%20spaces/file.png);"
        result = relativize_css_rule_list(css, "http://www.example.com/")
        assert "path%20with%20spaces" in result

    def test_unicode_url(self):
        """Test URLs with unicode characters."""
        css = "background: url(http://example.com/文件.png);"
        result = relativize_css_rule_list(css, "http://www.example.com/")
        assert "文件" in result

    def test_important_flag_preserved(self):
        """Test that !important is preserved."""
        css = "background: url(http://example.com/bg.png) !important;"
        result = relativize_css_rule_list(css, "http://www.example.com/")
        assert "!important" in result

    def test_empty_url(self):
        """Test empty url() function."""
        css = "background: url();"
        result = relativize_css_rule_list(css, "http://www.example.com/")
        assert result == css  # Should handle gracefully

    def test_protocol_relative(self):
        """Test protocol-relative URLs."""
        css = "background: url(//example.com/bg.png);"
        result = relativize_css_rule_list(css, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/bg.png" in result

    def test_https_url(self):
        """Test HTTPS URLs."""
        css = "background: url(https://example.com/bg.png);"
        result = relativize_css_rule_list(css, "http://www.example.com/")
        assert "https%3A%2F%2Fexample.com/bg.png" in result

    def test_css_variable_urls(self):
        """Test URLs in CSS custom properties."""
        css = """
        :root {
            --bg-image: url(http://example.com/bg.png);
        }
        .test {
            background: var(--bg-image);
        }
        """
        result = relativize_stylesheet(css, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/bg.png" in result

    def test_media_queries(self):
        """Test URLs inside media queries."""
        css = """
        @media (min-width: 1000px) {
            .test {
                background: url(http://example.com/large.png);
            }
        }
        @media (max-width: 500px) {
            .test {
                background: url(http://example.com/small.png);
            }
        }
        """
        result = relativize_stylesheet(css, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/large.png" in result
        assert "http%3A%2F%2Fexample.com/small.png" in result

    def test_keyframes(self):
        """Test URLs inside @keyframes."""
        css = """
        @keyframes fadeIn {
            from { background: url(http://example.com/start.png); opacity: 0; }
            to { background: url(http://example.com/end.png); opacity: 1; }
        }
        """
        result = relativize_stylesheet(css, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/start.png" in result
        assert "http%3A%2F%2Fexample.com/end.png" in result

    def test_font_face(self):
        """Test URLs in @font-face."""
        css = """
        @font-face {
            font-family: 'Custom';
            src: url(http://example.com/font.woff2) format('woff2');
        }
        """
        result = relativize_stylesheet(css, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/font.woff2" in result

    def test_multiple_properties(self):
        """Test CSS with multiple URL properties."""
        css = """
        .test {
            background: url(http://example.com/bg.png);
            border-image: url(http://example.com/border.png);
            mask: url(http://example.com/mask.png);
        }
        """
        result = relativize_stylesheet(css, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/bg.png" in result
        assert "http%3A%2F%2Fexample.com/border.png" in result
        assert "http%3A%2F%2Fexample.com/mask.png" in result

    def test_bytes_input(self):
        """Test that bytes input is handled correctly."""
        css = b".test { background: url(http://example.com/bg.png); }"
        result = relativize_stylesheet(css, "http://www.example.com/")
        assert isinstance(result, str)
        assert "http%3A%2F%2Fexample.com/bg.png" in result

    def test_invalid_input_type(self):
        """Test that invalid input types raise TypeError."""
        with pytest.raises(TypeError):
            relativize_stylesheet(123, "http://www.example.com/")

    def test_preserves_other_css(self):
        """Test that non-URL CSS is preserved."""
        css = """
        .test {
            color: red;
            font-size: 16px;
            background: url(http://example.com/bg.png);
        }
        """
        result = relativize_stylesheet(css, "http://www.example.com/")
        assert "color: red" in result
        assert "font-size: 16px" in result

    def test_complex_selector(self):
        """Test complex selectors with URLs."""
        css = """
        div.container > p.text + span.highlight::after {
            content: url(http://example.com/icon.png);
        }
        """
        result = relativize_stylesheet(css, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/icon.png" in result

    def test_url_with_port(self):
        """Test URLs with ports."""
        css = "background: url(http://example.com:8080/bg.png);"
        result = relativize_css_rule_list(css, "http://www.example.com/")
        assert "example.com%3A8080" in result

    def test_url_with_credentials(self):
        """Test URLs with credentials."""
        css = "background: url(http://user:pass@example.com/bg.png);"
        result = relativize_css_rule_list(css, "http://www.example.com/")
        assert "user%3Apass%40example.com" in result

    def test_no_urls(self):
        """Test CSS with no URLs."""
        css = """
        .test {
            color: red;
            font-weight: bold;
        }
        """
        result = relativize_stylesheet(css, "http://www.example.com/")
        assert "color: red" in result
        assert "font-weight: bold" in result

    def test_relative_depth(self):
        """Test that relative depth is calculated correctly."""
        # Document at depth 1
        css = "background: url(http://example.com/bg.png);"
        result = relativize_css_rule_list(css, "http://www.example.com/page/")
        # Should have 2 levels of ../ (depth + 1)
        assert "../../http%3A%2F%2Fexample.com/bg.png" in result

    def test_root_relative_depth(self):
        """Test root-relative URLs with depth."""
        css = "background: url(/assets/bg.png);"
        result = relativize_css_rule_list(css, "http://www.example.com/page/")
        # Should navigate up to host root then into assets
        assert "../assets/bg.png" in result

    def test_mixed_url_types(self):
        """Test CSS with mixed URL types."""
        css = """
        .test {
            background: url(http://example.com/absolute.png);
            border-image: url(/root/relative.png);
            mask: url(./dot/relative.png);
        }
        """
        result = relativize_stylesheet(css, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/absolute.png" in result
        assert "root/relative.png" in result
        assert "dot/relative.png" in result

    def test_fragment_only(self):
        """Test URL with only fragment."""
        css = "background: url(#gradient);"
        result = relativize_css_rule_list(css, "http://www.example.com/")
        assert "#gradient" in result

    def test_whitespace_handling(self):
        """Test that whitespace around URLs is handled."""
        css = "background: url(  http://example.com/bg.png  );"
        result = relativize_css_rule_list(css, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/bg.png" in result

    def test_encoded_url(self):
        """Test already encoded URLs."""
        css = "background: url(http%3A%2F%2Fexample.com%2Fbg.png);"
        result = relativize_css_rule_list(css, "http://www.example.com/")
        assert "example.com" in result

    def test_complex_real_world(self):
        """Test complex real-world CSS scenario."""
        css = """
        /* Main stylesheet */
        @import url(http://fonts.example.com/font.css);

        @font-face {
            font-family: 'Custom';
            src: url(http://fonts.example.com/font.woff2) format('woff2');
        }

        .header {
            background: url(http://cdn.example.com/bg.png) no-repeat;
            background-image: url(http://cdn.example.com/bg-responsive.png);
        }

        @media (max-width: 768px) {
            .header {
                background: url(http://cdn.example.com/bg-mobile.png);
            }
        }

        .icon {
            mask: url(http://icons.example.com/icon.svg);
            -webkit-mask: url(http://icons.example.com/icon.svg);
        }

        :root {
            --hero-bg: url(http://cdn.example.com/hero.jpg);
        }
        """
        result = relativize_stylesheet(css, "http://www.example.com/")

        # All URLs should be relativized
        assert "http%3A%2F%2Ffonts.example.com/font.css" in result
        assert "http%3A%2F%2Ffonts.example.com/font.woff2" in result
        assert "http%3A%2F%2Fcdn.example.com/bg.png" in result
        assert "http%3A%2F%2Fcdn.example.com/bg-responsive.png" in result
        assert "http%3A%2F%2Fcdn.example.com/bg-mobile.png" in result
        assert "http%3A%2F%2Ficons.example.com/icon.svg" in result
        assert "http%3A%2F%2Fcdn.example.com/hero.jpg" in result

        # Original URLs should not appear
        assert "http://fonts.example.com" not in result
        assert "http://cdn.example.com" not in result
        assert "http://icons.example.com" not in result

    def test_multiple_import_urls(self):
        """Test multiple URLs in a single import-like context."""
        css = """
        .grid {
            background-image:
                url(http://example.com/a.png),
                url(http://example.com/b.png),
                url(http://example.com/c.png);
        }
        """
        result = relativize_stylesheet(css, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/a.png" in result
        assert "http%3A%2F%2Fexample.com/b.png" in result
        assert "http%3A%2F%2Fexample.com/c.png" in result

    def test_path_with_query_and_fragment(self):
        """Test URLs with both query string and fragment."""
        css = "background: url(http://example.com/bg.png?v=1.2#section);"
        result = relativize_css_rule_list(css, "http://www.example.com/")
        assert "?v=1.2" in result
        assert "#section" in result

    def test_multiple_files_referenced(self):
        """Test CSS that references multiple different files."""
        css = """
        .test {
            font-family: url(http://fonts.example.com/font.woff);
            background: url(http://images.example.com/bg.jpg);
            border: url(http://borders.example.com/border.png);
        }
        """
        result = relativize_stylesheet(css, "http://www.example.com/")
        assert "http%3A%2F%2Ffonts.example.com/font.woff" in result
        assert "http%3A%2F%2Fimages.example.com/bg.jpg" in result
        assert "http%3A%2F%2Fborders.example.com/border.png" in result


class TestIframeSrcdoc:
    """Tests for URL relativization in iframe srcdoc attributes.

    The srcdoc attribute contains HTML that needs its own URL relativization.
    """

    def test_srcdoc_absolute_urls(self):
        """Test that URLs in iframe srcdoc are relativized."""
        html = """
        <iframe srcdoc='<a href="http://example.com/page">Link</a>'></iframe>
        """
        result = relativize_html(html, "http://www.example.com/")
        # The srcdoc content should have relativized URLs
        assert "http%3A%2F%2Fexample.com/page" in result

    def test_srcdoc_relative_urls(self):
        """Test that relative URLs in srcdoc are resolved correctly."""
        html = """
        <iframe srcdoc='<a href="/root/relative">Link</a>'></iframe>
        """
        result = relativize_html(html, "http://www.example.com/page/")
        # Should become relative to the srcdoc's context
        assert "root/relative" in result or "../root/relative" in result

    def test_srcdoc_with_images(self):
        """Test images in srcdoc."""
        html = """
        <iframe srcdoc='<img src="http://example.com/image.png">'
        ></iframe>
        """
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/image.png" in result

    def test_srcdoc_with_scripts(self):
        """Test script sources in srcdoc."""
        html = """
        <iframe srcdoc='<script src="http://example.com/script.js"><'/script>'
        ></iframe>
        """
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/script.js" in result

    def test_srcdoc_with_styles(self):
        """Test style tags in srcdoc."""
        html = """
        <iframe srcdoc='<style>.test { background: url(http://example.com/bg.png); }</style>'
        ></iframe>
        """
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/bg.png" in result

    def test_nested_iframes(self):
        """Test iframes inside iframes."""
        outer = BeautifulSoup("<iframe></iframe>", "html.parser")
        inner = BeautifulSoup(
            """
        <iframe srcdoc=\"<a href='http://example.com/deep'>Link</a>\"></iframe>
        """,
            "html.parser",
        )
        outer.insert(0, inner)
        html = str(outer)
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/deep" in result

    def test_srcdoc_special_schemes(self):
        """Test special schemes in srcdoc are preserved."""
        html = """
        <iframe srcdoc='<a href="mailto:user@example.com">Mail</a>'></iframe>
        """
        result = relativize_html(html, "http://www.example.com/")
        assert "mailto:user@example.com" in result

    def test_srcdoc_preserves_content(self):
        """Test that srcdoc content structure is preserved."""
        html = """
        <iframe srcdoc='<div class="test"><p>Content</p></div>'></iframe>
        """
        result = relativize_html(html, "http://www.example.com/")
        assert 'class="test"' in result
        assert "&lt;div" in result
        assert "Content" in result


class TestSVG:
    """Extended SVG tests."""

    def test_svg_use_href(self):
        """Test SVG <use> element with href."""
        html = """
        <svg>
            <use href="http://example.com/symbols.svg#icon"/>
            <use xlink:href="http://example.com/symbols2.svg#icon2"/>
        </svg>
        """
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/symbols.svg" in result
        assert "http%3A%2F%2Fexample.com/symbols2.svg" in result

    def test_svg_pattern_href(self):
        """Test SVG <pattern> with href."""
        html = """
        <svg>
            <pattern id="p" href="http://example.com/pattern.svg"/>
        </svg>
        """
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/pattern.svg" in result

    def test_svg_gradient_links(self):
        """Test SVG gradient elements (rare but possible)."""
        html = """
        <svg>
            <radialGradient href="http://example.com/gradient.svg"/>
        </svg>
        """
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/gradient.svg" in result


class TestDataUriSVGAndHTML:
    """Tests for SVG and HTML data in URIs."""

    def test_svg_data_uri_with_urls(self):
        """Test SVG data URI containing URL references."""
        # SVG with external image reference
        svg_content = """<svg xmlns="http://www.w3.org/2000/svg">
            <image href="http://example.com/bg.png"/>
        </svg>"""
        encoded = base64.b64encode(svg_content.encode()).decode()
        html = f'<img src="data:image/svg+xml;base64,{encoded}">'
        result = relativize_html(html, "http://www.example.com/")
        assert "data:image/svg+xml" in result
        bs = BeautifulSoup(result, "html.parser")
        b64_data = (
            bs.find("img")["src"]
            .removeprefix("data:image/svg+xml;base64,")
            .encode()
        )
        svg_data = base64.b64decode(b64_data).decode()
        assert "../http%3A%2F%2Fexample.com/bg.png" in svg_data

    def test_svg_data_uri_plain(self):
        """Test plain SVG data URI without encoding."""
        svg = '<svg><image href="http://example.com/image.png"/></svg>'
        html = f"<img src='data:image/svg+xml,{svg}'>"
        result = relativize_html(html, "http://www.example.com/")
        assert "data:image/svg+xml" in result
        assert "../http%3A%2F%2Fexample.com/image.png" in result

    def test_data_html_base64(self):
        """Test base64 encoded HTML data URI."""
        html_content = '<a href="http://example.com/page">Link</a>'
        encoded = base64.b64encode(html_content.encode()).decode()
        data_uri = f"data:text/html;base64,{encoded}"
        html = f'<iframe src="{data_uri}"></iframe>'
        result = relativize_html(html, "http://www.example.com/")
        assert "data:text/html;base64" in result
        bs = BeautifulSoup(result, "html.parser")
        b64_data = (
            bs.find("iframe")["src"]
            .removeprefix("data:text/html;base64,")
            .encode()
        )
        data = base64.b64decode(b64_data).decode()
        assert "../http%3A%2F%2Fexample.com/page" in data

    def test_svg_data_uri_with_params(self):
        """Test plain SVG data URI with extra parameters."""
        svg = '<svg><image href="http://example.com/image.png"/></svg>'
        html = f"<img src='data:image/svg+xml;charset=UTF-8;my-cool-param=1,{svg}'>"
        result = relativize_html(html, "http://www.example.com/")
        assert "data:image/svg+xml" in result
        assert "../http%3A%2F%2Fexample.com/image.png" in result
        assert "charset=UTF-8" in result
        assert "my-cool-param=1" in result

    def test_css_data_uri_plain(self):
        """Test a plain CSS data URI containing URL references."""
        css_content = """.test { content: url(http://example.com/bg.png); }"""
        html = f'<link rel="stylesheet" href="data:text/css,{css_content}">'
        result = relativize_html(html, "http://www.example.com/")
        assert "data:text/css" in result
        assert "../http%3A%2F%2Fexample.com/bg.png" in result

    def test_css_data_uri_base64(self):
        """Test a base64n CSS data URI containing URL references."""
        css_content = """.test { content: url(http://example.com/bg.png); }"""
        encoded = base64.b64encode(css_content.encode()).decode()
        html = f'<link rel="stylesheet" href="data:text/css;base64,{encoded}">'
        result = relativize_html(html, "http://www.example.com/")
        assert "data:text/css" in result
        bs = BeautifulSoup(result, "html.parser")
        b64_data = (
            bs.find("link")["href"]
            .removeprefix("data:text/css;base64,")
            .encode()
        )
        svg_data = base64.b64decode(b64_data).decode()
        assert "../http%3A%2F%2Fexample.com/bg.png" in svg_data

    def test_data_html_plain(self):
        """Test that data URIs with internal links are handled."""
        html = """
        <img src="data:text/html,<a href='https://example.com/page'></a>" />
        """
        result = relativize_html(html, "http://www.example.com/")
        assert "data:text/html" in result
        assert "../https%3A%2F%2Fexample.com/page" in result

    def test_data_uri_not_modified(self):
        """Test that data URIs are not modified by URL relativization."""
        data_uri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA"
        html = f'<img src="{data_uri}">'
        result = relativize_html(html, "http://www.example.com/")
        assert data_uri in result


class TestInlineStyles:
    """Tests for URLs in inline <style> tags.

    These require CSS relativization within HTML context.
    """

    def test_style_tag_urls(self):
        """Test URLs in <style> tags are relativized."""
        html = """
        <style>
            .test { background: url(http://example.com/bg.png); }
        </style>
        """
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/bg.png" in result

    def test_style_import(self):
        """Test @import in style tags."""
        html = """
        <style>
            @import url(http://example.com/import.css);
        </style>
        """
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/import.css" in result

    def test_style_font_face(self):
        """Test @font-face in style tags."""
        html = """
        <style>
            @font-face {
                font-family: 'Test';
                src: url(http://example.com/font.woff2);
            }
        </style>
        """
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/font.woff2" in result

    def test_style_media_queries(self):
        """Test URLs in media queries inside style tags."""
        html = """
        <style>
            @media (min-width: 1000px) {
                .test { background: url(http://example.com/large.png); }
            }
        </style>
        """
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/large.png" in result

    def test_style_keyframes(self):
        """Test URLs in keyframes inside style tags."""
        html = """
        <style>
            @keyframes fadeIn {
                from { background: url(http://example.com/start.png); }
                to { background: url(http://example.com/end.png); }
            }
        </style>
        """
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/start.png" in result
        assert "http%3A%2F%2Fexample.com/end.png" in result

    def test_style_multiple_urls(self):
        """Test multiple URLs in style tags."""
        html = """
        <style>
            .grid {
                background-image:
                    url(http://example.com/a.png),
                    url(http://example.com/b.png);
            }
        </style>
        """
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/a.png" in result
        assert "http%3A%2F%2Fexample.com/b.png" in result

    def test_style_preserves_other(self):
        """Test that non-URL CSS in style tags is preserved."""
        html = """
        <style>
            .test {
                color: red;
                font-size: 16px;
                background: url(http://example.com/bg.png);
            }
        </style>
        """
        result = relativize_html(html, "http://www.example.com/")
        assert "color: red" in result
        assert "font-size: 16px" in result


class TestObjectEmbed:
    """Tests for <object> and <embed> with document data.

    These can reference external documents that need relativization.
    """

    def test_object_data_url(self):
        """Test object data attribute."""
        html = '<object data="http://example.com/document.pdf"></object>'
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/document.pdf" in result

    def test_embed_src_url(self):
        """Test embed src attribute."""
        html = '<embed src="http://example.com/plugin.swf" type="application/x-shockwave-flash">'
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/plugin.swf" in result

    def test_object_codebase(self):
        """Test object codebase attribute."""
        html = '<object codebase="http://example.com/base/"></object>'
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/base/" in result


class TestShadowDOM:
    """Tests for Shadow DOM URL handling.

    Note: Shadow DOM content in HTML files is typically represented as
    <template shadowroot> elements in parsed HTML.
    """

    def test_shadowroot_urls(self):
        """Test URLs in shadowroot templates."""
        html = """
        <template shadowroot="open">
            <a href="http://example.com/link">Link</a>
            <img src="http://example.com/image.png">
        </template>
        """
        result = relativize_html(html, "http://www.example.com/")
        # Shadow root content should be relativized too
        assert "http%3A%2F%2Fexample.com/link" in result
        assert "http%3A%2F%2Fexample.com/image.png" in result

    def test_shadowroot_styles(self):
        """Test styles in shadowroot."""
        html = """
        <template shadowroot="open">
            <style>
                .test { background: url(http://example.com/bg.png); }
            </style>
        </template>
        """
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/bg.png" in result


class TestNestedDocuments:
    """Tests for nested document scenarios."""

    def test_picture_sources(self):
        """Test <picture> element with multiple sources."""
        html = """
        <picture>
            <source srcset="http://example.com/large.webp" type="image/webp">
            <source srcset="http://example.com/large.jpg" type="image/jpeg">
            <img src="http://example.com/fallback.jpg">
        </picture>
        """
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/large.webp" in result
        assert "http%3A%2F%2Fexample.com/large.jpg" in result
        assert "http%3A%2F%2Fexample.com/fallback.jpg" in result

    def test_video_sources(self):
        """Test <video> with multiple source elements."""
        html = """
        <video poster="http://example.com/poster.jpg">
            <source src="http://example.com/video.mp4" type="video/mp4">
            <source src="http://example.com/video.webm" type="video/webm">
            <track src="http://example.com/captions.vtt" kind="subtitles">
        </video>
        """
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/poster.jpg" in result
        assert "http%3A%2F%2Fexample.com/video.mp4" in result
        assert "http%3A%2F%2Fexample.com/video.webm" in result
        assert "http%3A%2F%2Fexample.com/captions.vtt" in result

    def test_audio_sources(self):
        """Test <audio> with multiple sources."""
        html = """
        <audio>
            <source src="http://example.com/audio.mp3" type="audio/mpeg">
            <source src="http://example.com/audio.ogg" type="audio/ogg">
        </audio>
        """
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/audio.mp3" in result
        assert "http%3A%2F%2Fexample.com/audio.ogg" in result

    def test_map_areas(self):
        """Test image map areas."""
        html = """
        <map name="map">
            <area href="http://example.com/region1" shape="rect">
            <area href="http://example.com/region2" shape="circle">
            <area href="http://example.com/region3" shape="poly">
        </map>
        """
        result = relativize_html(html, "http://www.example.com/")
        assert "http%3A%2F%2Fexample.com/region1" in result
        assert "http%3A%2F%2Fexample.com/region2" in result
        assert "http%3A%2F%2Fexample.com/region3" in result


class TestComplexIntegration:
    """Integration tests combining multiple recursive cases."""

    def test_full_document_with_all_recursions(self):
        """Test a document with all types of recursive content."""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                @import url(http://fonts.example.com/font.css);
                .test { background: url(http://cdn.example.com/bg.png); }
                @font-face { src: url(http://fonts.example.com/font.woff2); }
            </style>
        </head>
        <body>
            <div>
                <img src="http://images.example.com/image.png">
                <svg>
                    <image href="http://svg.example.com/svg-image.png"/>
                    <use href="http://svg.example.com/use.svg#icon"/>
                </svg>
                <iframe srcdoc='<a href="http://iframe.example.com/link">Link</a>'></iframe>
                <object data="http://object.example.com/data.pdf"></object>
                <picture>
                    <source srcset="http://pic.example.com/large.webp">
                    <img src="http://pic.example.com/fallback.jpg">
                </picture>
            </div>
        </body>
        </html>
        """
        result = relativize_html(html, "http://www.example.com/")

        # All URLs should be relativized
        assert "http%3A%2F%2Ffonts.example.com/font.css" in result
        assert "http%3A%2F%2Fcdn.example.com/bg.png" in result
        assert "http%3A%2F%2Ffonts.example.com/font.woff2" in result
        assert "http%3A%2F%2Fimages.example.com/image.png" in result
        assert "http%3A%2F%2Fsvg.example.com/svg-image.png" in result
        assert "http%3A%2F%2Fsvg.example.com/use.svg" in result
        assert "http%3A%2F%2Fiframe.example.com/link" in result
        assert "http%3A%2F%2Fobject.example.com/data.pdf" in result
        assert "http%3A%2F%2Fpic.example.com/large.webp" in result
        assert "http%3A%2F%2Fpic.example.com/fallback.jpg" in result

        # Original URLs should not appear
        assert "http://fonts.example.com" not in result
        assert "http://cdn.example.com" not in result
        assert "http://images.example.com" not in result
        assert "http://svg.example.com" not in result
        assert "http://iframe.example.com" not in result
        assert "http://object.example.com" not in result
        assert "http://pic.example.com" not in result

    def test_depth_handling_in_nested(self):
        """Test that depth is correctly handled in nested content."""
        html = """
        <div>
            <style>
                .test { background: url(http://example.com/bg.png); }
            </style>
            <iframe srcdoc='<style>.inner { background: url(http://example.com/inner.png); }</style>'></iframe>
        </div>
        """
        result = relativize_html(html, "http://www.example.com/page/")

        assert "http%3A%2F%2Fexample.com/bg.png" in result
        assert "http%3A%2F%2Fexample.com/inner.png" in result
