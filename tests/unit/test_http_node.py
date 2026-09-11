import pytest
from pydantic import ValidationError

from wysteria.ir.models import HttpConfig, HttpNode, Node


def test_valid_get_http_node():
    config = HttpConfig(method="GET", url="https://api.example.com/data")
    assert config.method == "GET"
    assert config.url == "https://api.example.com/data"

    node = HttpNode(
        id="fetch1",
        output_type="object",
        kind="http",
        config=config,
    )
    assert node.id == "fetch1"
    assert node.kind == "http"


def test_valid_post_http_node():
    config = HttpConfig(method="POST", url="http://example.com/api")
    assert config.method == "POST"


def test_invalid_http_method():
    with pytest.raises(ValidationError):
        HttpConfig(method="OPTIONS", url="https://example.com")


def test_file_url_rejected():
    with pytest.raises(ValidationError, match="url scheme must be http or https"):
        HttpConfig(method="GET", url="file:///etc/passwd")


def test_ftp_url_rejected():
    with pytest.raises(ValidationError, match="url scheme must be http or https"):
        HttpConfig(method="GET", url="ftp://example.com/file")


def test_localhost_rejected():
    with pytest.raises(ValidationError, match="localhost and loopback urls are not permitted"):
        HttpConfig(method="GET", url="http://localhost:8080/api")


def test_127_0_0_1_rejected():
    with pytest.raises(ValidationError, match="localhost and loopback urls are not permitted"):
        HttpConfig(method="GET", url="http://127.0.0.1/api")


def test_ipv6_loopback_rejected():
    with pytest.raises(ValidationError, match="localhost and loopback urls are not permitted"):
        HttpConfig(method="GET", url="http://[::1]:8080/api")


def test_headers_accepted():
    config = HttpConfig(
        method="GET",
        url="https://api.example.com",
        headers={"Authorization": "Bearer token", "Accept": "application/json"},
    )
    assert config.headers["Authorization"] == "Bearer token"


def test_node_union_parsing():
    import pydantic

    class Wrapper(pydantic.BaseModel):
        node: Node

    # Verify HttpNode works in the union
    obj = Wrapper.model_validate(
        {
            "node": {
                "id": "n1",
                "kind": "http",
                "output_type": "string",
                "config": {"method": "GET", "url": "https://example.com"},
            }
        }
    )
    assert isinstance(obj.node, HttpNode)
    assert obj.node.config.url == "https://example.com"

    # Verify existing ConstantNode still works in the union
    obj2 = Wrapper.model_validate(
        {
            "node": {
                "id": "n2",
                "kind": "constant",
                "output_type": "string",
                "config": {"value": "hello"},
            }
        }
    )
    from wysteria.ir.models import ConstantNode

    assert isinstance(obj2.node, ConstantNode)
    assert obj2.node.config.value == "hello"
