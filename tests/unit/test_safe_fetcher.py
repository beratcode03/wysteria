import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

import pytest

from wysteria.evidence.fetcher import (
    BlockedAddressError,
    ConnectionFailureError,
    DNSResolutionError,
    InvalidURLError,
    ResponseTooLargeError,
    SafeFetcher,
    TooManyRedirectsError,
    UnsupportedSchemeError,
    _is_private_ip,
)


def test_is_private_ip_matrix():
    # 1. SSRF matrix explicit tests
    assert _is_private_ip("127.0.0.1")
    assert _is_private_ip("0.0.0.0")
    assert _is_private_ip("10.0.0.1")
    assert _is_private_ip("172.16.0.1")
    assert _is_private_ip("192.168.1.1")
    assert _is_private_ip("169.254.169.254")
    assert _is_private_ip("::1")

    # IPv4-mapped IPv6
    assert _is_private_ip("::ffff:127.0.0.1")
    assert _is_private_ip("::ffff:10.0.0.1")
    assert _is_private_ip("::ffff:169.254.169.254")

    # Invalid IPs
    assert _is_private_ip("not.an.ip")

    # Public IPs
    assert not _is_private_ip("8.8.8.8")
    assert not _is_private_ip("93.184.216.34")


# --- Offline Mock Server Setup ---
class MockHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/public":
            self.send_response(200)
            self.send_header("Content-Length", "5")
            self.end_headers()
            self.wfile.write(b"Hello")
        elif self.path == "/redirect-public":
            self.send_response(302)
            self.send_header("Location", "http://example.com/public")
            self.end_headers()
        elif self.path == "/redirect-private":
            self.send_response(302)
            self.send_header("Location", "http://169.254.169.254/metadata")
            self.end_headers()
        elif self.path == "/redirect-localhost":
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1/admin")
            self.end_headers()
        elif self.path == "/redirect-loop":
            self.send_response(302)
            self.send_header("Location", "http://example.com/redirect-loop")
            self.end_headers()
        elif self.path == "/downgrade":
            self.send_response(302)
            self.send_header("Location", "http://example.com/public")
            self.end_headers()
        elif self.path == "/large-no-content-length":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"A" * 1500)
        elif self.path == "/chunked":
            self.send_response(200)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            self.wfile.write(b"5\r\nHello\r\n0\r\n\r\n")
        elif self.path == "/check-auth":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(str(self.headers).encode())
        elif self.path == "/timeout":
            import time
            time.sleep(0.5)
            self.send_response(200)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


@pytest.fixture(scope="module")
def mock_server():
    server = HTTPServer(("127.0.0.1", 0), MockHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    yield server
    server.shutdown()


@pytest.fixture
def mock_dns_and_socket(mock_server):
    port = mock_server.server_port
    orig_getaddrinfo = socket.getaddrinfo
    orig_socket_connect = socket.socket.connect
    orig_create_connection = socket.create_connection

    def fake_getaddrinfo(host, *args, **kwargs):
        if host == "example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]
        elif host == "mixed.com":
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", port)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))
            ]
        elif host == "private-only.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", port))]
        elif host in ("exämple.com", "xn--exmple-cua.com"):
            raise socket.gaierror("Mock DNS resolution failed")
        else:
            return orig_getaddrinfo(host, *args, **kwargs)

    def fake_socket_connect(self, address):
        if isinstance(address, tuple) and len(address) == 2:
            host, _ = address
            if host == "93.184.216.34":
                return orig_socket_connect(self, ("127.0.0.1", port))
        return orig_socket_connect(self, address)

    def fake_create_connection(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):
        if isinstance(address, tuple) and len(address) == 2:
            host, _ = address
            if host == "93.184.216.34":
                return orig_create_connection(("127.0.0.1", port), timeout, source_address)
        return orig_create_connection(address, timeout, source_address)

    with patch("socket.getaddrinfo", side_effect=fake_getaddrinfo):
        with patch("socket.socket.connect", side_effect=fake_socket_connect, autospec=True):
            with patch("socket.create_connection", side_effect=fake_create_connection):
                yield port


# --- 2. Redirect Tests ---

def test_redirect_public_to_public(mock_dns_and_socket):
    fetcher = SafeFetcher()
    res = fetcher.get("http://example.com/redirect-public")
    assert res.status_code == 200
    assert res.body == b"Hello"


def test_redirect_public_to_private(mock_dns_and_socket):
    fetcher = SafeFetcher()
    with pytest.raises(BlockedAddressError) as exc:
        fetcher.get("http://example.com/redirect-private")
    assert "SSRF block" in str(exc.value)


def test_redirect_public_to_localhost(mock_dns_and_socket):
    fetcher = SafeFetcher()
    with pytest.raises(BlockedAddressError) as exc:
        fetcher.get("http://example.com/redirect-localhost")
    assert "SSRF block" in str(exc.value)


def test_redirect_loop(mock_dns_and_socket):
    fetcher = SafeFetcher(max_redirects=3)
    with pytest.raises(TooManyRedirectsError):
        fetcher.get("http://example.com/redirect-loop")


def test_mixed_dns_result(mock_dns_and_socket):
    fetcher = SafeFetcher()
    # mixed.com returns 10.0.0.1 and 93.184.216.34.
    # SafeFetcher strips private IPs and connects to the public one.
    res = fetcher.get("http://mixed.com/public")
    assert res.status_code == 200
    assert res.body == b"Hello"


def test_private_only_dns(mock_dns_and_socket):
    fetcher = SafeFetcher()
    with pytest.raises(BlockedAddressError):
        fetcher.get("http://private-only.com/public")


# --- 3. Proxy Bypass Tests ---

def test_proxy_ignored(mock_dns_and_socket, monkeypatch):
    # Set proxy environments. SafeFetcher should ignore them and connect directly.
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:8080")
    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:1080")

    fetcher = SafeFetcher()
    res = fetcher.get("http://example.com/public")
    assert res.status_code == 200
    assert res.body == b"Hello"


# --- 4. URL Parsing Tests ---

def test_malformed_url():
    fetcher = SafeFetcher()
    with pytest.raises(InvalidURLError):
        fetcher.get("not-a-url")

    with pytest.raises(InvalidURLError):
        fetcher.get("http://")


def test_unsupported_scheme():
    fetcher = SafeFetcher()
    with pytest.raises(UnsupportedSchemeError):
        fetcher.get("file:///etc/passwd")


def test_url_userinfo(mock_dns_and_socket):
    # Credentials in URL are strictly blocked by SafeFetcher to prevent leakage
    # or obscure SSRF bypasses.
    fetcher = SafeFetcher()
    with pytest.raises(InvalidURLError, match="Credentials in URL are not allowed for security reasons"):
        fetcher.get("http://user:pass@example.com/check-auth")


def test_unicode_punycode_hostname(mock_dns_and_socket):
    # This just ensures we don't crash on unicode, though getaddrinfo mocks will fall through
    # if not handled, generating a DNS error, which is safe.
    fetcher = SafeFetcher()
    with pytest.raises(DNSResolutionError):
        fetcher.get("http://exämple.com/public")


# --- 5. Resource Limits Tests ---

def test_large_response_no_content_length(mock_dns_and_socket):
    fetcher = SafeFetcher(max_size=1000)
    with pytest.raises(ResponseTooLargeError):
        fetcher.get("http://example.com/large-no-content-length")


def test_chunked_response(mock_dns_and_socket):
    fetcher = SafeFetcher()
    res = fetcher.get("http://example.com/chunked")
    assert res.status_code == 200
    assert res.body == b"Hello"


def test_timeout(mock_dns_and_socket):
    fetcher = SafeFetcher(timeout=0.1)
    with pytest.raises(ConnectionFailureError) as exc:
        fetcher.get("http://example.com/timeout")
    assert "Timeout" in str(exc.value)


# --- 6. Credential / Header Leakage ---

def test_no_credentials_sent(mock_dns_and_socket):
    fetcher = SafeFetcher()
    res = fetcher.get("http://example.com/check-auth")
    # Body contains headers returned by our mock server
    body_str = res.body.decode()
    assert "Authorization" not in body_str
    assert "Cookie" not in body_str
    assert "User-Agent" in body_str
