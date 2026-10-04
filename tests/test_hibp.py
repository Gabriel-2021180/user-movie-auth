import asyncio
import hashlib

import httpx
import pytest

from app.core.config import settings
from app.integrations import hibp

PASSWORD = "contraseña-de-prueba-123"
_DIGEST = hashlib.sha1(PASSWORD.encode("utf-8")).hexdigest().upper()


@pytest.fixture
def hibp_on(monkeypatch):
    monkeypatch.setattr(settings, "HIBP_ENABLED", True)
    seen = []
    real = httpx.AsyncClient

    def use(handler):
        def recording(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return handler(request)

        monkeypatch.setattr(hibp.httpx, "AsyncClient",
                            lambda **kw: real(transport=httpx.MockTransport(recording), **kw))
        return seen

    return use


def _check() -> bool:
    return asyncio.run(hibp.is_breached(PASSWORD))


def test_breached_password_detected_and_only_prefix_sent(hibp_on):
    seen = hibp_on(lambda r: httpx.Response(200, text=f"0000000000000000000000000000000000A:3\r\n{_DIGEST[5:]}:42\r\n"))
    assert _check() is True
    url = str(seen[0].url)
    assert url.endswith(f"/range/{_DIGEST[:5]}")
    assert _DIGEST[5:] not in url and PASSWORD not in url
    assert seen[0].headers["add-padding"] == "true"


def test_padding_entries_with_zero_count_ignored(hibp_on):
    hibp_on(lambda r: httpx.Response(200, text=f"{_DIGEST[5:]}:0\r\n"))
    assert _check() is False


def test_not_breached(hibp_on):
    hibp_on(lambda r: httpx.Response(200, text="0000000000000000000000000000000000A:3\r\n"))
    assert _check() is False


def test_service_down_does_not_block(hibp_on):
    def boom(request):
        raise httpx.ConnectError("caído")

    hibp_on(boom)
    assert _check() is False
    hibp_on(lambda r: httpx.Response(503))
    assert _check() is False


def test_disabled_makes_no_request(monkeypatch):
    monkeypatch.setattr(settings, "HIBP_ENABLED", False)
    monkeypatch.setattr(hibp.httpx, "AsyncClient", None)  # fallaría si se usara
    assert _check() is False
