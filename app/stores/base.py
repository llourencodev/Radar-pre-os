"""Ferramentas comuns aos coletores: extrair JSON embutido, achar produtos em qualquer JSON e em HTML."""
import json
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..matching import parse_price


@dataclass
class Offer:
    store: str
    title: str
    price: float
    url: str
    old_price: float | None = None
    image: str | None = None
    seller: str | None = None
    installments: str | None = None
    condition: str | None = None        # novo | usado | recondicionado
    kind: str = "produto"               # produto (loja) | promo (comunidade de promoções)
    via: str | None = None              # loja real quando a oferta veio de um comparador/comunidade
    coupon: str | None = None
    posted_at: str | None = None
    note: str | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class StoreResult:
    store: str
    offers: list[Offer] = field(default_factory=list)
    status: str = "ok"                   # ok | vazio | bloqueado | erro
    error: str | None = None
    seen: int = 0                        # itens lidos antes do filtro de relevância


# ------------------------------------------------------------------ JSON embutido nas páginas
def next_data(html: str) -> dict | None:
    m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def ld_json(html: str) -> list:
    out = []
    for m in re.finditer(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            out.append(json.loads(m.group(1).strip()))
        except ValueError:
            continue
    return out


def json_after(html: str, marker: str) -> object | None:
    """Lê o objeto JSON que começa logo depois de `marker` (contando chaves, respeitando strings)."""
    i = html.find(marker)
    if i < 0:
        return None
    i = html.find("{", i + len(marker))
    if i < 0:
        return None
    depth, in_str, esc = 0, False, False
    for j in range(i, min(len(html), i + 8_000_000)):
        c = html[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[i:j + 1])
                except ValueError:
                    return None
    return None


_DECODER = json.JSONDecoder()


def next_flight(html: str) -> list:
    """Next.js App Router: junta os pedaços `self.__next_f.push([1,"..."])` e lê os JSONs de cada linha `id:[...]`."""
    parts = []
    for m in re.finditer(r'self\.__next_f\.push\(\[1,\s*("(?:[^"\\]|\\.)*")\]\)', html, re.S):
        try:
            parts.append(json.loads(m.group(1)))
        except ValueError:
            continue
    flight = "".join(parts)
    out, pos = [], 0
    rx = re.compile(r"[0-9a-f]{1,5}:(?=[\[{])")
    while True:
        m = rx.search(flight, pos)
        if not m:
            break
        try:
            obj, pos = _DECODER.raw_decode(flight, m.end())
            out.append(obj)
        except ValueError:
            pos = m.end()
    return out


def _astro_value(v):
    """Astro serializa props como [tipo, valor]; 0 = valor simples/objeto, 1 = lista."""
    if isinstance(v, list) and v and isinstance(v[0], int):
        if len(v) == 1:
            return None
        kind, val = v[0], v[1]
        if kind == 1 and isinstance(val, list):
            return [_astro_value(x) for x in val]
        if isinstance(val, dict):
            return {k: _astro_value(x) for k, x in val.items()}
        return val
    if isinstance(v, dict):
        return {k: _astro_value(x) for k, x in v.items()}
    return v


def astro_props(html: str) -> list:
    """Props das <astro-island> (usadas pelo Pelando), já convertidas para JSON comum."""
    import html as _html
    out = []
    for m in re.finditer(r'<astro-island\b[^>]*?\sprops="([^"]*)"', html):
        try:
            out.append(_astro_value(json.loads(_html.unescape(m.group(1)))))
        except ValueError:
            continue
    return out


def all_blobs(html: str) -> list:
    """Todos os blocos JSON conhecidos que lojas costumam embutir no HTML."""
    blobs = []
    nd = next_data(html)
    if nd:
        blobs.append(nd)
    blobs.extend(ld_json(html))
    for marker in ("__PRELOADED_STATE__", "__APOLLO_STATE__", "_init_data_= { data: ", "__INITIAL_STATE__",
                   "__STATE__", "window.__data"):
        b = json_after(html, marker)
        if b:
            blobs.append(b)
    if "self.__next_f" in html:
        blobs.extend(next_flight(html))
    if "<astro-island" in html:
        blobs.extend(astro_props(html))
    return blobs


def walk(obj, depth: int = 0):
    if depth > 40:
        return
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            if isinstance(v, str) and len(v) > 50 and v[:1] in "{[":
                try:
                    yield from walk(json.loads(v), depth + 1)
                except ValueError:
                    pass
            else:
                yield from walk(v, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v, depth + 1)


TITLE_KEYS = ("name", "title", "productName", "displayTitle", "offerTitle", "product_name", "nome", "titulo", "headline")
# ordem = preferência (à vista/pix antes do parcelado)
PRICE_KEYS = (
    "priceWithDiscount", "price_with_discount", "pixPrice", "pix_price", "price_pix", "avista", "cashPrice", "spotPrice",
    "bestPrice", "best_price", "salePrice", "sale_price", "offerPrice", "final_price", "finalPrice", "sellingPrice",
    "currentPrice", "lowPrice", "price", "preco", "minPrice", "value",
)
OLD_PRICE_KEYS = ("oldPrice", "old_price", "listPrice", "list_price", "originalPrice", "original_price", "priceFrom",
                  "fullPrice", "full_price", "regularPrice", "regular_price", "highPrice", "offerOldPrice", "price_before_discount")
URL_KEYS = ("url", "link", "permalink", "productUrl", "product_url", "href", "path", "url_key", "canonicalUrl", "sourceUrl")
IMAGE_KEYS = ("image", "imageUrl", "image_url", "thumbnail", "img", "imgUrl", "picture", "photo", "offerPhoto", "thumb")


def _first_str(d: dict, keys) -> str | None:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            for kk in ("displayTitle", "url", "src", "imgUrl", "value", "name"):
                if isinstance(v.get(kk), str) and v[kk].strip():
                    return v[kk].strip()
        if isinstance(v, list) and v and isinstance(v[0], str):
            return v[0]
        if isinstance(v, list) and v and isinstance(v[0], dict):
            s = _first_str(v[0], ("url", "src", "imgUrl", "image"))
            if s:
                return s
    return None


def price_of(d: dict, keys=PRICE_KEYS) -> float | None:
    for k in keys:
        if k in d:
            v = d[k]
            if isinstance(v, dict):
                # ex.: {"bestPrice": "2229.99", "price": "2499.00"} ou {"avista": ..., "final_price": ...}
                p = price_of(v, keys) if any(kk in v for kk in keys) else parse_price(v)
            else:
                p = parse_price(v)
            if p:
                return p
    for nested in ("price", "pichau_prices", "prices", "priceInfo", "offers", "offer", "pricing", "price_range", "minimum_price"):
        v = d.get(nested)
        if isinstance(v, dict):
            p = price_of(v, keys)
            if p:
                return p
    return None


def offers_from_json(blobs: list, store: str, base_url: str, url_builder=None, kind: str = "produto") -> list[Offer]:
    """Procura, em qualquer JSON, objetos com cara de produto (título + preço + link)."""
    out, seen = [], set()
    for blob in blobs:
        for d in walk(blob):
            title = _first_str(d, TITLE_KEYS)
            if not title or len(title) < 8:
                continue
            price = price_of(d)
            if not price:
                continue
            url = (url_builder(d) if url_builder else None) or _first_str(d, URL_KEYS)
            if not url:
                continue
            url = urljoin(base_url, url)
            if not url.startswith("http") or url in seen:
                continue
            seen.add(url)
            old = price_of(d, OLD_PRICE_KEYS)
            img = _first_str(d, IMAGE_KEYS)
            out.append(Offer(store=store, title=title, price=price, url=url, kind=kind,
                             old_price=old if old and old > price else None,
                             image=urljoin(base_url, img) if img else None))
    return out


# ------------------------------------------------------------------ HTML genérico
_PRICE_TXT = re.compile(r"R\$\s*\d{1,3}(?:\.\d{3})*(?:,\d{2})?")


def offers_from_html(html: str, store: str, base_url: str, link_pattern: str, kind: str = "produto") -> list[Offer]:
    """Plano B: links de produto + o primeiro preço "R$" do cartão que envolve o link."""
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    rx = re.compile(link_pattern)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not rx.search(href):
            continue
        url = urljoin(base_url, href)
        if url in seen:
            continue
        title = (a.get("title") or a.get_text(" ", strip=True) or "").strip()
        card = a
        price_txt = []
        for _ in range(7):
            card = card.parent
            if card is None:
                break
            txt = card.get_text(" ", strip=True)
            price_txt = _PRICE_TXT.findall(txt)
            if price_txt:
                if len(title) < 8:
                    h = card.find(["h2", "h3", "h4"]) or card.find(attrs={"title": True})
                    title = (h.get("title") if h and h.get("title") else (h.get_text(" ", strip=True) if h else title))
                break
        if not price_txt or len(title) < 8:
            continue
        # preços menores que 1/20 do maior costumam ser parcela ("12x de R$ 199,90")
        prices = [p for p in (parse_price(t) for t in price_txt) if p]
        if not prices:
            continue
        top = max(prices)
        cands = [p for p in prices if p >= top / 6]
        price = min(cands)
        img_el = card.find("img") if card else None
        img = (img_el.get("src") or img_el.get("data-src")) if img_el else None
        seen.add(url)
        out.append(Offer(store=store, title=title, price=price, url=url, kind=kind,
                         old_price=top if top > price * 1.02 and top < price * 3 else None,
                         image=urljoin(base_url, img) if img and not img.startswith("data:") else None))
    return out


def slug(query: str, sep: str = "-") -> str:
    from ..matching import strip_accents
    return re.sub(r"[^a-z0-9]+", sep, strip_accents(query.lower())).strip(sep)
