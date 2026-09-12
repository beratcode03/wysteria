"""Safe external fetcher for evidence retrieval with strict SSRF protection."""

import ipaddress
import socket
import ssl
import urllib.error
import urllib.request
from http.client import HTTPConnection, HTTPSConnection
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel


class FetchError(Exception):
    """Base exception for evidence fetching errors."""

    pass


class InvalidURLError(FetchError):
    pass


class UnsupportedSchemeError(FetchError):
    pass


class BlockedAddressError(FetchError):
    pass


class DNSResolutionError(FetchError):
    pass


class TooManyRedirectsError(FetchError):
    pass


class ResponseTooLargeError(FetchError):
    pass


class ConnectionFailureError(FetchError):
    pass


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is private, loopback, link-local, or otherwise unsafe."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # If it's not a valid IP, block it

    # Handle IPv4-mapped IPv6 addresses (e.g., ::ffff:127.0.0.1)
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped

    # Check for specific ranges that might not be covered by is_private in all Python versions
    # We strictly block anything that is not a global unicast address or is reserved.
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True

    return False


def _safe_create_connection(
    address: tuple[str, int],
    timeout: float = socket._GLOBAL_DEFAULT_TIMEOUT,
    source_address: tuple[str, int] | None = None,
) -> socket.socket:
    """Create a socket connection with strict DNS resolution and SSRF checks."""
    host, port = address

    # Check if host is already an IP address
    try:
        ipaddress.ip_address(host)
        is_ip = True
    except ValueError:
        is_ip = False

    if is_ip:
        if _is_private_ip(host):
            raise BlockedAddressError(f"SSRF block: IP {host} is private or restricted")
        return socket.create_connection(address, timeout, source_address)

    # Resolve hostname
    try:
        # We only want TCP streams
        addrinfo = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise DNSResolutionError(f"DNS resolution failed for {host}") from e

    valid_ips = []
    for info in addrinfo:
        ip = info[4][0]
        if not _is_private_ip(ip):
            valid_ips.append(info)

    if not valid_ips:
        raise BlockedAddressError(f"SSRF block: {host} resolves only to private or restricted IPs")

    # Try connecting to the first valid IP
    err = None
    for info in valid_ips:
        af, socktype, proto, _, sa = info
        s = None
        try:
            s = socket.socket(af, socktype, proto)
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                s.settimeout(timeout)
            if source_address:
                s.bind(source_address)
            s.connect(sa)
            return s
        except OSError as _err:
            err = _err
            if s is not None:
                s.close()

    if err is not None:
        raise ConnectionFailureError(f"Failed to connect to valid IPs for {host}") from err
    else:
        raise ConnectionFailureError("getaddrinfo returned empty list")


class _SafeHTTPConnection(HTTPConnection):
    def connect(self) -> None:
        self.sock = _safe_create_connection(
            (self.host, self.port), self.timeout, self.source_address
        )


class _SafeHTTPSConnection(HTTPSConnection):
    def connect(self) -> None:
        self.sock = _safe_create_connection(
            (self.host, self.port), self.timeout, self.source_address
        )
        if self._tunnel_host:
            self._tunnel()
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


class _SafeHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req: urllib.request.Request) -> Any:
        return self.do_open(_SafeHTTPConnection, req)


class _SafeHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req: urllib.request.Request) -> Any:
        return self.do_open(
            _SafeHTTPSConnection, req, context=self._context, check_hostname=self._check_hostname
        )


class FetchResult(BaseModel):
    """Structured result of an external HTTP fetch."""

    url: str
    status_code: int
    headers: dict[str, str]
    body: bytes
    content_type: str | None


class SafeFetcher:
    """An SSRF-protected HTTP client for evidence retrieval."""

    def __init__(
        self,
        timeout: float = 5.0,
        max_size: int = 1048576,  # 1 MiB
        max_redirects: int = 3,
    ) -> None:
        self.timeout = timeout
        self.max_size = max_size
        self.max_redirects = max_redirects

    def get(self, url: str) -> FetchResult:
        """Fetch a URL safely using GET method only."""
        parsed = urlparse(url)
        if not parsed.scheme:
            raise InvalidURLError(f"Invalid URL: {url}")

        if parsed.scheme not in ("http", "https"):
            raise UnsupportedSchemeError(f"Unsupported URL scheme: {parsed.scheme}")

        if not parsed.netloc:
            raise InvalidURLError(f"Invalid URL, missing hostname: {url}")

        if parsed.username or parsed.password:
            raise InvalidURLError("Credentials in URL are not allowed for security reasons")

        class BoundRedirectHandler(urllib.request.HTTPRedirectHandler):
            max_redirects = self.max_redirects

            def redirect_request(
                self,
                req: urllib.request.Request,
                fp: Any,
                code: int,
                msg: str,
                headers: Any,
                newurl: str,
            ) -> urllib.request.Request:
                p = urlparse(newurl)
                if p.scheme not in ("http", "https"):
                    raise UnsupportedSchemeError(f"Redirect to unsupported scheme {p.scheme}")
                new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
                if not new_req:
                    raise TooManyRedirectsError("Too many redirects")
                if hasattr(req, "redirect_count"):
                    new_req.redirect_count = req.redirect_count + 1
                else:
                    new_req.redirect_count = 1

                if new_req.redirect_count > self.max_redirects:
                    raise TooManyRedirectsError("Too many redirects")
                return new_req

        opener = urllib.request.OpenerDirector()
        opener.add_handler(_SafeHTTPHandler())
        opener.add_handler(_SafeHTTPSHandler(context=ssl.create_default_context()))
        opener.add_handler(BoundRedirectHandler())
        opener.add_handler(urllib.request.HTTPErrorProcessor())

        # Minimal headers to prevent leaking sensitive info
        headers = {
            "User-Agent": "wysteria-evidence-fetcher/0.2",
            "Accept": "text/html,application/json,application/xhtml+xml,text/xml;q=0.9,*/*;q=0.8",
        }
        req = urllib.request.Request(url, method="GET", headers=headers)

        try:
            with opener.open(req, timeout=self.timeout) as response:
                return self._read_response(response)
        except urllib.error.HTTPError as e:
            # Server responded with an error code (4xx, 5xx)
            # We return this as a structured result rather than raising an exception.
            with e:
                return self._read_response(e)
        except urllib.error.URLError as e:
            if isinstance(e.reason, socket.timeout) or isinstance(e.reason, TimeoutError):
                raise ConnectionFailureError("Timeout during fetch") from e
            raise ConnectionFailureError(f"Connection failed: {e.reason}") from e
        except TimeoutError as e:
            raise ConnectionFailureError("Timeout during fetch") from e

    def _read_response(self, response: Any) -> FetchResult:
        status_code = response.status if hasattr(response, "status") else response.code
        headers_dict = dict(response.headers)
        content_type = response.headers.get("Content-Type")

        body = bytearray()
        while True:
            try:
                chunk = response.read(8192)
            except TimeoutError as e:
                raise ConnectionFailureError("Timeout during read") from e
            if not chunk:
                break
            body.extend(chunk)
            if len(body) > self.max_size:
                raise ResponseTooLargeError(
                    f"Response exceeded maximum size of {self.max_size} bytes"
                )

        return FetchResult(
            url=response.url,
            status_code=status_code,
            headers=headers_dict,
            body=bytes(body),
            content_type=content_type,
        )
