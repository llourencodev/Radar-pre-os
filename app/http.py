"""Cliente HTTP compartilhado com limite de requisições por site."""
import ssl
import threading
import time
from urllib.parse import quote, urlparse

import httpx

from . import config

_client: httpx.Client | None = None
_client_lock = threading.Lock()
_host_locks: dict[str, threading.Lock] = {}
_host_last: dict[str, float] = {}
_host_guard = threading.Lock()

BROWSER_HEADERS = {
    "User-Agent": config.USER_AGENT,
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}


def ssl_context() -> ssl.SSLContext:
    """Usa os certificados do sistema operacional (mesma cadeia do navegador)."""
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        return ssl.create_default_context()


def client() -> httpx.Client:
    global _client
    with _client_lock:
        if _client is None:
            _client = httpx.Client(
                headers=BROWSER_HEADERS,
                follow_redirects=True,
                verify=ssl_context(),
                timeout=httpx.Timeout(config.HTTP_TIMEOUT, connect=10),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                http2=False,
            )
        return _client


def _throttle(url: str) -> None:
    host = urlparse(url).netloc.lower()
    with _host_guard:
        lock = _host_locks.setdefault(host, threading.Lock())
    with lock:
        wait = _host_last.get(host, 0) + config.HOST_MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _host_last[host] = time.monotonic()


def ascii_url(url: str) -> str:
    return url if url.isascii() else quote(url, safe=":/?#[]@!$&'()*+,;=%~")


class Blocked(Exception):
    """A loja recusou a consulta (bloqueio anti-robô, captcha ou login)."""


def get(url: str, *, headers: dict | None = None, params: dict | None = None, json_api: bool = False) -> httpx.Response:
    url = ascii_url(url)
    _throttle(url)
    h = dict(headers or {})
    if json_api:
        h.setdefault("Accept", "application/json, text/plain, */*")
        h.setdefault("Sec-Fetch-Dest", "empty")
        h.setdefault("Sec-Fetch-Mode", "cors")
    r = client().get(url, headers=h, params=params)
    if r.status_code in (401, 403, 429, 503):
        raise Blocked(f"HTTP {r.status_code}: a loja bloqueou a consulta automática")
    _debug_dump(url, r)
    r.raise_for_status()
    low = r.text[:4000].lower()
    if "captcha" in low and "<html" in low and len(r.text) < 60000:
        raise Blocked("A loja pediu captcha (bloqueio anti-robô)")
    if "suspicious-traffic-frontend" in low or "account-verification" in low:
        raise Blocked("A loja exige verificação de conta/navegador (tráfego considerado suspeito)")
    if "bm-verify" in low or "/_sec/verify" in low:
        raise Blocked("A loja respondeu com desafio anti-robô (Akamai); só funciona em navegador")
    return r


def _debug_dump(url: str, r: httpx.Response) -> None:
    """Com PRECOS_DEBUG=1, guarda cada resposta em data/debug para ajustar coletores."""
    import os
    import re as _re
    if os.environ.get("PRECOS_DEBUG") != "1":
        return
    d = config.DATA_DIR / "debug"
    d.mkdir(exist_ok=True)
    name = _re.sub(r"[^a-zA-Z0-9]+", "_", url)[:120]
    (d / f"{name}_{r.status_code}.html").write_text(r.text, encoding="utf-8", errors="replace")


def post(url: str, **kw) -> httpx.Response:
    url = ascii_url(url)
    _throttle(url)
    r = client().post(url, **kw)
    if r.status_code in (401, 403, 429, 503):
        raise Blocked(f"HTTP {r.status_code}: a loja bloqueou a consulta automática")
    r.raise_for_status()
    return r
