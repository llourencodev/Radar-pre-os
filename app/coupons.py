"""Coleta de cupons de desconto das lojas monitoradas, a partir de sites agregadores de cupons."""
import logging
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from . import http
from .stores.base import all_blobs, walk

log = logging.getLogger(__name__)

# loja: {agregador: slug no agregador}
# (o Pelando só tem página de cupons para Amazon, Magalu, Mercado Livre, Shopee e AliExpress)
COUPON_STORES = {
    "KaBuM!": {"promobit": "kabum", "cuponomia": "kabum", "meliuz": "cupom-kabum"},
    "Pichau": {"promobit": "pichau", "cuponomia": "pichau", "meliuz": "cupom-pichau"},
    "Terabyte": {"promobit": "terabyteshop", "cuponomia": "terabyte-shop", "meliuz": "cupom-terabyteshop"},
    "Mercado Livre": {"pelando": "mercado-livre", "promobit": "mercado-livre", "cuponomia": "mercado-livre",
                      "meliuz": "cupom-mercado-livre"},
    "Magalu": {"pelando": "magalu", "promobit": "magazine-luiza", "cuponomia": "magazine-luiza", "meliuz": "cupom-magazine-luiza"},
    "Amazon": {"pelando": "amazon", "promobit": "amazon", "cuponomia": "amazon", "meliuz": "cupom-amazon"},
    "Americanas": {"promobit": "americanas", "cuponomia": "americanas", "meliuz": "cupom-americanas"},
    "Shopee": {"pelando": "shopee", "promobit": "shopee", "cuponomia": "shopee", "meliuz": "cupom-shopee"},
    "AliExpress": {"pelando": "aliexpress", "promobit": "aliexpress", "cuponomia": "aliexpress", "meliuz": "cupom-aliexpress"},
}
SOURCES = {
    "pelando": ("Pelando", "https://www.pelando.com.br/cupons-de-descontos/{}"),
    "promobit": ("Promobit", "https://www.promobit.com.br/cupons/loja/{}/"),
    "cuponomia": ("Cuponomia", "https://www.cuponomia.com.br/desconto/{}"),
    "meliuz": ("Méliuz", "https://www.meliuz.com.br/desconto/{}"),
}
PROMOBIT_API = "https://api.promobit.com.br/search/result/coupons"
_DATE = re.compile(r"(?:v[aá]lid[oa]|vale|expira|termina)[^.]{0,25}?\b(?:at[eé]|em)\s+(\d{1,2}/\d{1,2}(?:/\d{2,4})?)", re.I)
CODE_KEYS = ("couponCode", "coupon_code", "code", "codigo", "voucher", "promoCode")
TEXT_KEYS = ("title", "description", "name", "headline", "label", "text")
END_KEYS = ("endDate", "expiresAt", "expirationDate", "expiration", "validUntil", "end_date", "expires_at")
_BAD_CODES = {"null", "none", "undefined", "true", "false", "cupom", "codigo", "ver", "copiar", "pegar"}


@dataclass
class Coupon:
    store: str
    code: str | None
    title: str
    url: str
    source: str
    expires: str | None = None
    min_value: float | None = None
    pct: float | None = None
    amount: float | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def discount_of(text: str) -> tuple[float | None, float | None, float | None]:
    """(percentual, valor em reais, valor mínimo) lidos do texto do cupom."""
    t = (text or "").replace("\xa0", " ")
    pct = re.search(r"(\d{1,2}(?:[.,]\d)?)\s*%", t)
    amt = re.search(r"R\$\s*(\d[\d.,]*)\s*(?:de\s+)?(?:off|desconto|de desconto)", t, re.I)
    if not amt:
        amt = re.search(r"(?:desconto de|ganhe|cupom de)\s*R\$\s*(\d[\d.,]*)", t, re.I)
    mn = re.search(r"(?:acima de|a partir de|m[ií]nim[oa] de|compras de)\s*R\$\s*(\d{1,6}(?:\.\d{3})*)", t, re.I)
    f = lambda m: float(m.group(1).replace(".", "").replace(",", ".")) if m else None  # noqa: E731
    return f(pct), _amount(amt.group(1) if amt else None), f(mn)


_BRL = re.compile(r"\d{1,3}(?:\.\d{3})*(?:,\d{2})?|\d+(?:,\d{2})?")
MAX_AMOUNT = 2000.0  # desconto fixo acima disso é quase sempre valor mal escrito (ex.: "R$ 3.290.84")


def _amount(raw: str | None) -> float | None:
    """Valor em reais do desconto; None se o formato for inválido ou o valor for implausível."""
    if not raw:
        return None
    raw = raw.rstrip(".,")
    if not _BRL.fullmatch(raw):
        return None
    v = float(raw.replace(".", "").replace(",", "."))
    return v if 0 < v <= MAX_AMOUNT else None


def _valid_code(c) -> str | None:
    if not isinstance(c, str):
        return None
    c = c.strip()
    if not (3 <= len(c) <= 30) or " " in c or c.lower() in _BAD_CODES or c.startswith("http"):
        return None
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", c):
        return None
    return c


def _txt(el) -> str:
    return el.get_text(" ", strip=True) if el else ""


def _join(title: str, desc: str) -> str:
    """Título + regras (descrição) num texto só, sem repetir."""
    title, desc = (title or "").strip(), (desc or "").strip()
    if desc and desc.lower() not in title.lower():
        return f"{title} — {desc}"[:200]
    return title[:200]


def _expires(text: str) -> str | None:
    m = _DATE.search(text or "")
    return m.group(1) if m else None


def _cards(store: str, source: str, url: str, html: str) -> list[Coupon]:
    """Leitores específicos dos cartões de cupom de cada agregador (código, título, regras, validade)."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    # Cuponomia: <li data-type="code"> .js-couponSmallText (desconto) .js-itemTitle .item-desc .js-itemCode
    for li in soup.select('li[data-type="code"]'):
        code = _valid_code(_txt(li.select_one(".js-itemCode")))
        title = _txt(li.select_one(".js-itemTitle"))
        if not (code and title):
            continue
        short, desc = _txt(li.select_one(".js-couponSmallText")), _txt(li.select_one(".item-desc"))
        out.append(Coupon(store, code, _join(f"{short}: {title}" if short and short not in title else title, desc),
                          url, source, _expires(desc)))
    # Méliuz: <div class="offer-cpn" data-offer-code data-offer-title> + regras no texto do cartão
    for el in soup.select("[data-offer-code]"):
        code = _valid_code(el.get("data-offer-code"))
        title = (el.get("data-offer-title") or "").strip()
        if not (code and title):
            continue
        txt = _txt(el)
        desc = txt.rsplit(code, 1)[-1].strip(" |") if code in txt else ""
        out.append(Coupon(store, code, _join(title, desc), el.get("data-offer-url") or url, source, _expires(txt)))
    # Pelando: <article class="card"> com botão data-copy-code
    for art in soup.select("article"):
        btn = art.select_one("[data-copy-code]")
        code = _valid_code(btn.get("data-copy-code")) if btn else None
        if not code:
            continue
        h = art.select_one("h3, h2, [class*=title]")
        title = _txt(h)
        if not title:
            isl = art.select_one('astro-island[component-export="DealCardShare"]')
            title = (re.search(r'"title":\[0,"([^"]+)"', isl.get("props", "")) or [None, ""])[1] if isl else ""
        link = art.select_one('a[href*="/d/"]')
        out.append(Coupon(store, code, (title or code)[:200],
                          ("https://www.pelando.com.br" + link["href"]) if link and link["href"].startswith("/") else url,
                          source, _expires(_txt(art))))
    return out


def _promobit(store: str, slug: str) -> list[Coupon]:
    """Promobit: API pública de busca de cupons (traz código, título, regras e validade)."""
    data = http.get(PROMOBIT_API, params={"q": slug.replace("-", " ")}, json_api=True,
                    headers={"Origin": "https://www.promobit.com.br", "Referer": "https://www.promobit.com.br/"}).json()
    out = []
    for c in data.get("coupons") or []:
        code = _valid_code(c.get("coupon_code"))
        if c.get("store_slug") != slug or not code or c.get("coupon_status_name", "APPROVED") != "APPROVED":
            continue
        title = c.get("coupon_title") or c.get("coupon_discount") or code
        if c.get("coupon_discount") and c["coupon_discount"].lower() not in title.lower():
            title = f"{c['coupon_discount']}: {title}"
        cp = Coupon(store, code, _join(title, c.get("coupon_instructions") or ""),
                    "https://www.promobit.com.br" + c["coupon_url"] if str(c.get("coupon_url", "")).startswith("/")
                    else SOURCES["promobit"][1].format(slug),
                    "Promobit", c.get("coupon_until") or _expires(c.get("coupon_instructions") or ""))
        cp.pct, cp.amount, cp.min_value = discount_of(f"{c.get('coupon_discount', '')} {cp.title}")
        out.append(cp)
    return out


def _from_page(store: str, source: str, url: str, html: str) -> list[Coupon]:
    out = _cards(store, source, url, html)
    seen = {c.code.lower() for c in out if c.code}
    for blob in ([] if out else all_blobs(html)):
        for d in walk(blob):
            code = next((_valid_code(d.get(k)) for k in CODE_KEYS if _valid_code(d.get(k))), None)
            title = next((d[k].strip() for k in TEXT_KEYS if isinstance(d.get(k), str) and len(d[k].strip()) > 6), None)
            if not title or not (code or re.search(r"%|R\$", title)):
                continue
            key = (code or title).lower()
            if key in seen:
                continue
            seen.add(key)
            end = next((d[k] for k in END_KEYS if isinstance(d.get(k), str)), None)
            out.append(Coupon(store, code, title[:200], url, source, end))
    if not out:  # plano B: botões "copiar cupom" no HTML
        soup = BeautifulSoup(html, "html.parser")
        for el in soup.select("[data-code], [data-coupon], [data-clipboard-text], [data-coupon-code]"):
            code = _valid_code(el.get("data-code") or el.get("data-coupon") or el.get("data-clipboard-text") or el.get("data-coupon-code"))
            if not code or code.lower() in seen:
                continue
            box = el
            for _ in range(5):
                box = box.parent or box
                if len(box.get_text(" ", strip=True)) > 25:
                    break
            seen.add(code.lower())
            out.append(Coupon(store, code, box.get_text(" ", strip=True)[:200], url, source))
    for c in out:
        c.pct, c.amount, c.min_value = discount_of(c.title)
    return out


def fetch_store(store: str) -> tuple[list[Coupon], list[str]]:
    coupons, errors = [], []
    for src, slug in COUPON_STORES.get(store, {}).items():
        name, tpl = SOURCES[src]
        url = tpl.format(slug)
        try:
            if src == "promobit":
                coupons.extend(_promobit(store, slug))
            else:
                coupons.extend(_from_page(store, name, url, http.get(url).text))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {e}")
            log.info("cupons %s via %s falhou: %s", store, name, e)
    return coupons, errors


def score(c: dict, ref_price: float | None = None) -> float:
    """Economia estimada em R$ para um produto do preço de referência (ou para R$ 1.000)."""
    base = ref_price or 1000.0
    if c.get("min_value") and base < c["min_value"]:
        return 0.0
    vals = []
    if c.get("pct"):
        vals.append(base * c["pct"] / 100)
    if c.get("amount"):
        vals.append(c["amount"])
    return max(vals) if vals else 0.0
