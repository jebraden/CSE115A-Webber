from src.urlreplace import relativize_html_url


class TestRelativizeHTMLUrl:
    def assert_urls(self, document_url: str, urls: list[tuple[str, str]]):
        for original, output in urls:
            assert relativize_html_url(original, document_url) == output

    def test_absolute(self):
        """Absolute URLs resolve against some specified host."""
        self.assert_urls(
            "http://www.example.com/",
            [
                ("http://example.com/", "http%3A%2F%2Fexample.com/"),
                ("https://www.example.com/", "https%3A%2F%2Fwww.example.com/"),
                (
                    "https://www.example.com/a/b.html",
                    "https%3A%2F%2Fwww.example.com/a/b.html",
                ),
                (
                    "https://www.example.com/a/b.html?param1=val&param2=val#fragment",
                    "https%3A%2F%2Fwww.example.com/a/b.html?param1=val&param2=val#fragment",
                ),
            ],
        )

    def test_protocol_relative(self):
        """Protocol-relative URLs resolve against document's protocol."""
        self.assert_urls(
            "http://www.example.com/",
            [
                ("//example.com/path", "http%3A%2F%2Fexample.com/path"),
                (
                    "//example.com:8080/path",
                    "http%3A%2F%2Fexample.com%3A8080/path",
                ),
                (
                    "//cdn.example.com/script.js",
                    "http%3A%2F%2Fcdn.example.com/script.js",
                ),
                (
                    "//user:pass@example.com/file",
                    "http%3A%2F%2Fuser%3Apass@example.com/file",
                ),
            ],
        )
        self.assert_urls(
            "https://www.example.com/",
            [
                ("//example.com/path", "https%3A%2F%2Fexample.com/path"),
                (
                    "//example.com:8080/path",
                    "https%3A%2F%2Fexample.com%3A8080/path",
                ),
            ],
        )

    def test_root_relative(self):
        """Root-relative URLs resolve against document's host."""
        self.assert_urls(
            "http://www.example.com/",
            [
                ("/path/file", "http%3A%2F%2Fwww.example.com/path/file"),
                ("/", "http%3A%2F%2Fwww.example.com/"),
                ("/css/main.css", "http%3A%2F%2Fwww.example.com/css/main.css"),
                (
                    "/api/data?query=1",
                    "http%3A%2F%2Fwww.example.com/api/data?query=1",
                ),
            ],
        )

    def test_document_relative(self):
        """Document-relative URLs resolve against document's path."""
        self.assert_urls(
            "http://www.example.com/page/",
            [
                ("path/file", "http%3A%2F%2Fwww.example.com/page/path/file"),
                ("./path/file", "http%3A%2F%2Fwww.example.com/page/path/file"),
                ("../path/file", "http%3A%2F%2Fwww.example.com/path/file"),
                ("../../path/file", "http%3A%2F%2Fwww.example.com/path/file"),
                (
                    "img/logo.png",
                    "http%3A%2F%2Fwww.example.com/page/img/logo.png",
                ),
            ],
        )

    def test_fragment_only(self):
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

    def test_data_uri(self):
        """Data URIs are self-contained and should be preserved."""
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
                # TODO actually, these can contain links!
                (
                    "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg'>",
                    "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg'>",
                ),
            ],
        )

    def test_blob_url(self):
        """Blob URLs are temporary, but will be captured by playwright."""
        self.assert_urls(
            "http://www.example.com/",
            [
                (
                    "blob:http://example.com/uuid-1234",
                    "http%3A%2F%2Fexample.com/uuid-1234",
                ),
                (
                    "blob:https://example.com/uuid-5678",
                    "https%3A%2F%2Fexample.com/uuid-5679",
                ),
                (
                    "blob:http://localhost/8f34f9d6-385e-483b-9eff-fea4b9e9b9b6",
                    "http%3A%2F%2Flocalhost/8f34f9d6-385e-483b-9eff-fea4b9e9b9b6",
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
                ("?param=value", "http%3A%2F%2Fwww.example.com/?param=value"),
                ("path?query=1", "http%3A%2F%2Fwww.example.com/path?query=1"),
                (
                    "path?param1=val&param2=val",
                    "http%3A%2F%2Fwww.example.com/path?param1=val&param2=val",
                ),
                (
                    "https://example.com/api?format=json&type=html",
                    "https%3A%2F%2Fexample.com/api?format=json&type=html",
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
                    "http%3A%2F%2Fwww.example.com/http%3A%2F%2Fexample.com%2Fpath",
                ),
            ],
        )

    def test_ports(self):
        """Ports should be encoded."""
        self.assert_urls(
            "http://www.example.com/",
            [
                (
                    "http://example.com:8080/path",
                    "http%3A%2F%2Fexample.com%3A8080/path",
                ),
                (
                    "https://example.com:443/path",
                    "https%3A%2F%2Fexample.com%3A443/path",
                ),
                (
                    "https://example.com:444/path",
                    "https%3A%2F%2Fexample.com%3A444/path",
                ),
                (
                    "//example.com:8080/path",
                    "http%3A%2F%2Fexample.com%3A8080/path",
                ),
                (
                    "//example.com:80/path",
                    "http%3A%2F%2Fexample.com/path",
                ),
            ],
        )

    def test_credentials(self):
        """Credentials should be encoded."""
        self.assert_urls(
            "http://www.example.com/",
            [
                (
                    "http://user:pass@example.com/",
                    "http%3A%2F%2Fuser%3Apass%40example.com/",
                ),
                (
                    "https://user@example.com/",
                    "https%3A%2F%2Fuser%40example.com/",
                ),
                (
                    "//user:pass@example.com/file",
                    "http%3A%2F%2Fuser%3Apass%40example.com/file",
                ),
            ],
        )

    def test_fragments_with_url(self):
        """Fragments should be preserved when attached to URLs."""
        self.assert_urls(
            "http://www.example.com/",
            [
                ("path#section", "http%3A%2F%2Fwww.example.com/path#section"),
                (
                    "https://example.com/page#fragment",
                    "https%3A%2F%2Fexample.com/page#fragment",
                ),
                (
                    "https://example.com/page?query=1#frag",
                    "https%3A%2F%2Fexample.com/page?query=1#frag",
                ),
                ("#fragment", "#fragment"),  # Fragment only
            ],
        )

    def test_empty_and_whitespace(self):
        """Whitespace should be removed."""
        self.assert_urls(
            "http://www.example.com/",
            [
                ("", ""),
                ("   ", ""),
                ("\t\n", ""),
                ("  http://example.com  ", "http%3A%2F%2Fexample.com"),
            ],
        )

    def test_complex_urls(self):
        """Complex URLs with multiple components."""
        self.assert_urls(
            "http://www.example.com/",
            [
                (
                    "https://user:pass@example.com:8080/path?query=1#frag",
                    "https%3A%2F%2Fuser%3Apass@example.com%3A8080/path?query=1#frag",
                ),
                (
                    "//user:pass@example.com:8080/path",
                    "http%3A%2F%2Fuser%3Apass@example.com%3A8080/path",
                ),
                (
                    "https://example.com/path/to/file?param1=val&param2=val#section",
                    "https%3A%2F%2Fexample.com/path/to/file?param1=val&param2=val#section",
                ),
            ],
        )

    def test_relative_resolution(self):
        """Test relative URL resolution against different document paths."""
        self.assert_urls(
            "http://www.example.com/a/b/c.html",
            [
                ("d/e.png", "http%3A%2F%2Fwww.example.com/a/b/d/e.png"),
                ("../d/e.png", "http%3A%2F%2Fwww.example.com/a/d/e.png"),
                ("../../d/e.png", "http%3A%2F%2Fwww.example.com/d/e.png"),
                ("./d/e.png", "http%3A%2F%2Fwww.example.com/a/b/d/e.png"),
            ],
        )

    def test_mixed_case(self):
        """URLs should preserve case."""
        self.assert_urls(
            "http://www.example.com/",
            [
                ("HTTP://EXAMPLE.COM/PATH", "HTTP%3A%2F%2FEXAMPLE.COM/PATH"),
                ("https://Example.Com/Path", "https%3A%2F%2FExample.Com/Path"),
            ],
        )

    def test_unicode(self):
        """Unicode URLs should be handled."""
        self.assert_urls(
            "http://www.example.com/",
            [
                ("https://example.com/文件", "https%3A%2F%2Fexample.com/文件"),
                ("https://example.com/файл", "https%3A%2F%2Fexample.com/файл"),
            ],
        )
