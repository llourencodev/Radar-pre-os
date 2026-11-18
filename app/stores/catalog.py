"""Coletores por loja. Cada um recebe o texto da busca e devolve as ofertas encontradas.

Os sites mudam com frequência; por isso cada coletor tenta primeiro a fonte de dados mais estável
(API ou JSON embutido na página) e depois um plano B genérico pelo HTML.
"""
import re
from urllib.parse import quote, quote_plus

from bs4 import BeautifulSoup

from .. import config, http
from ..matching import parse_price
from .base import Offer, all_blobs, offers_from_html, offers_from_json, slug, walk

_USED = re.compile(r"\b(usad[oa]s?|seminov[oa]|recondicionad[oa]|vitrine|desmontad[oa]|open ?box|testad[oa] ok)\b", re.I)


def condition_of(title: str) -> str | None:
    return "usado" if _USED.search(title or "") else None


# ------------------------------------------------------------------ Mercado Livre
def _ml_api(q: str) -> list[Offer]:
    """API oficial do Mercado Livre (precisa de ML_ACCESS_TOKEN; veja o README)."""
    r = http.get("https://api.mercadolibre.com/sites/MLB/search", params={"q": q, "limit": 50}, json_api=True,
                 headers={"Authorization": f"Bearer {config.ML_ACCESS_TOKEN}"})
    out = []
    for it in r.json().get("results") or []:
        price = parse_price(it.get("price"))
        if not price or not it.get("permalink"):
            continue
        old = parse_price(it.get("original_price"))
        seller = (it.get("seller") or {}).get("nickname")
        out.append(Offer(store="Mercado Livre", title=it.get("title") or "", price=price, url=it["permalink"],
                         old_price=old if old and old > price else None, image=it.get("thumbnail"), seller=seller,
                         condition="usado" if it.get("condition") == "used" else condition_of(it.get("title"))))
    return out


def mercadolivre(q: str) -> list[Offer]:
    if config.ML_ACCESS_TOKEN:
        try:
            return _ml_api(q)
        except http.Blocked as e:
            raise http.Blocked(f"A API do Mercado Livre recusou o token (expirado ou inválido): {e}") from e
    try:
        return _mercadolivre_site(q)
    except http.Blocked as e:
        raise http.Blocked(f"{e}. Configure ML_ACCESS_TOKEN no .env para usar a API oficial (veja o README).") from e


def _mercadolivre_site(q: str) -> list[Offer]:
    out: list[Offer] = []
    for suffix in ("", "_OrderId_PRICE"):
        url = f"https://lista.mercadolivre.com.br/{slug(q)}{suffix}_NoIndex_True"
        html = http.get(url).text
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("li.ui-search-layout__item, div.poly-card, div.ui-search-result__wrapper")
        for c in cards:
            a = c.select_one("a.poly-component__title, h2 a, h3 a, a.ui-search-link, a.ui-search-item__group__element")
            if not a or not a.get("href"):
                continue
            title = a.get_text(" ", strip=True) or a.get("title", "")
            cur = c.select_one(".poly-price__current, .ui-search-price__second-line, .andes-money-amount:not(.andes-money-amount--previous)")
            frac = cur.select_one(".andes-money-amount__fraction") if cur else None
            if not frac:
                continue
            cents = cur.select_one(".andes-money-amount__cents")
            price = parse_price(f"{frac.get_text(strip=True)},{cents.get_text(strip=True) if cents else '00'}")
            prev = c.select_one("s.andes-money-amount--previous .andes-money-amount__fraction")
            img = c.select_one("img")
            seller = c.select_one(".poly-component__seller")
            inst = c.select_one(".poly-price__installments, .ui-search-installments")
            cond = "usado" if "usado" in c.get_text(" ", strip=True).lower()[:400] else None
            if price:
                out.append(Offer(
                    store="Mercado Livre", title=title, price=price, url=a["href"].split("#")[0],
                    old_price=parse_price(prev.get_text(strip=True)) if prev else None,
                    image=(img.get("data-src") or img.get("src")) if img else None,
                    seller=seller.get_text(" ", strip=True) if seller else None,
                    installments=inst.get_text(" ", strip=True) if inst else None, condition=cond))
        if not out:
            out = offers_from_json(all_blobs(html), "Mercado Livre", "https://www.mercadolivre.com.br/")
    return out


# ------------------------------------------------------------------ KaBuM!
def kabum(q: str) -> list[Offer]:
    out: list[Offer] = []
    try:
        r = http.get("https://servicespub.prod.api.aws.grupokabum.com.br/catalog/v2/products",
                     params={"query": q, "page_size": 100, "page_number": 1, "sort": "most_searched", "include": "gift"},
                     json_api=True, headers={"Origin": "https://www.kabum.com.br", "Referer": "https://www.kabum.com.br/"})
        for item in r.json().get("data", []):
            at = item.get("attributes", item)
            pid = item.get("id") or at.get("code")
            title = at.get("title") or at.get("name")
            offer = at.get("offer") or {}
            price = (parse_price(offer.get("price_with_discount")) or parse_price(at.get("price_with_discount"))
                     or parse_price(offer.get("price")) or parse_price(at.get("price")))
            if not (pid and title and price) or at.get("available") is False:
                continue
            imgs = at.get("images") or at.get("photos") or []
            out.append(Offer(store="KaBuM!", title=title, price=price, url=f"https://www.kabum.com.br/produto/{pid}",
                             old_price=parse_price(at.get("old_price")),
                             image=imgs[0] if imgs and isinstance(imgs[0], str) else None,
                             note="Oferta relâmpago" if offer else None))
    except Exception:
        out = []
    if out:
        return out
    html = http.get(f"https://www.kabum.com.br/busca/{slug(q)}?page_size=100").text

    def build(d):
        code = d.get("code") or d.get("id")
        return f"https://www.kabum.com.br/produto/{code}" if str(code or "").isdigit() else None
    out = offers_from_json(all_blobs(html), "KaBuM!", "https://www.kabum.com.br/", url_builder=build)
    return out or offers_from_html(html, "KaBuM!", "https://www.kabum.com.br/", r"/produto/\d+")


# ------------------------------------------------------------------ Magazine Luiza
def magalu(q: str) -> list[Offer]:
    html = http.get(f"https://www.magazineluiza.com.br/busca/{quote_plus(q)}/").text
    offers = offers_from_json(all_blobs(html), "Magalu", "https://www.magazineluiza.com.br/")
    for o in offers:
        if o.image:
            o.image = o.image.replace("{w}x{h}", "280x210")
    return offers or offers_from_html(html, "Magalu", "https://www.magazineluiza.com.br/", r"/p/[a-z0-9]+/")


# ------------------------------------------------------------------ Pichau
def pichau(q: str, pages: int = 3) -> list[Offer]:
    out, seen, first_html = [], set(), None
    for page in range(1, pages + 1):
        html = http.get(f"https://www.pichau.com.br/search?q={quote(q)}" + (f"&page={page}" if page > 1 else "")).text
        first_html = first_html or html
        before = len(seen)
        out.extend(_pichau_items(html, seen))
        if len(seen) == before:   # página sem produtos novos = fim
            break
    if out:
        return out
    html = first_html

    def build(d):
        k = d.get("url_key")
        return f"https://www.pichau.com.br/{k}" if k else None
    offers = offers_from_json(all_blobs(html), "Pichau", "https://www.pichau.com.br/", url_builder=build)
    return offers or offers_from_html(html, "Pichau", "https://www.pichau.com.br/", r"^/(?!search|categoria|login|carrinho)[a-z0-9-]{25,}$")


def _pichau_items(html: str, seen: set) -> list[Offer]:
    out = []
    # Next.js App Router: cada produto traz pichau_prices {avista (Pix), final_price (parcelado), base_price}
    for d in (x for b in all_blobs(html) for x in walk(b)):
        pp = d.get("pichau_prices")
        if not (isinstance(pp, dict) and d.get("url_key") and d.get("name")) or d["url_key"] in seen:
            continue
        seen.add(d["url_key"])
        if d.get("stock_status") and d["stock_status"] != "IN_STOCK":
            continue
        price = parse_price(pp.get("avista")) or parse_price(pp.get("final_price"))
        if not price:
            continue
        old = parse_price(pp.get("base_price"))
        img = d.get("image") if isinstance(d.get("image"), dict) else {}
        n, parc = pp.get("max_installments"), parse_price(pp.get("min_installment_price"))
        out.append(Offer(store="Pichau", title=d["name"], price=price, url=f"https://www.pichau.com.br/{d['url_key']}",
                         old_price=old if old and old > price else None,
                         image=img.get("url_listing") or img.get("url"),
                         installments=f"{n}x de R$ {parc:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if n and parc else None,
                         condition="usado" if d.get("is_openbox") else condition_of(d["name"]),
                         note=f"Preço no {pp.get('avista_method') or 'Pix'}" if pp.get("avista") else None))
    return out


# ------------------------------------------------------------------ Terabyte
def terabyte(q: str) -> list[Offer]:
    html = http.get(f"https://www.terabyteshop.com.br/busca?str={quote_plus(q)}").text
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for c in soup.select("div.product-item, div.pbox, div.commerce_columns_item_inner"):
        a = c.select_one("a.product-item__name, a.prod-name, h2 a, a[href*='/produto/']")
        p = c.select_one(".product-item__new-price, .prod-new-price, .new-price")
        if not a or not p:
            continue
        price = parse_price(p.get_text(" ", strip=True))
        old = c.select_one(".product-item__old-price, .prod-old-price")
        img = c.select_one("img")
        if price and "esgotado" not in c.get_text(" ", strip=True).lower():
            out.append(Offer(store="Terabyte", title=(a.get("title") or a.get_text(" ", strip=True)), price=price,
                             url=a["href"] if a["href"].startswith("http") else "https://www.terabyteshop.com.br" + a["href"],
                             old_price=parse_price(old.get_text(" ", strip=True)) if old else None,
                             image=(img.get("src") or img.get("data-src")) if img else None))
    return out or offers_from_html(html, "Terabyte", "https://www.terabyteshop.com.br/", r"/produto/\d+")


# ------------------------------------------------------------------ Americanas
def americanas(q: str) -> list[Offer]:
    try:
        return vtex_search("Americanas", "https://www.americanas.com.br", q)
    except http.Blocked:
        raise
    except Exception:  # noqa: BLE001 - cai para o HTML
        pass
    html = http.get(f"https://www.americanas.com.br/busca/{slug(q)}").text
    offers = offers_from_json(all_blobs(html), "Americanas", "https://www.americanas.com.br/")
    return offers or offers_from_html(html, "Americanas", "https://www.americanas.com.br/", r"/produto/|/p(\?|$)")


def vtex_search(store: str, base: str, q: str, pages: int = 2) -> list[Offer]:
    """Lojas VTEX (Americanas): API pública intelligent-search; o preço Pix/à vista vem em spotPrice."""
    out, seen = [], set()
    for page in range(1, pages + 1):
        r = http.get(f"{base}/api/io/_v/api/intelligent-search/product_search/",
                     params={"query": q, "count": 50, "page": page, "locale": "pt-BR", "hideUnavailableItems": "true"},
                     json_api=True)
        prods = r.json().get("products") or []
        for p in prods:
            link = p.get("link") or (f"/{p['linkText']}/p" if p.get("linkText") else None)
            if not link or link in seen:
                continue
            best = None
            for it in p.get("items") or []:
                for s in it.get("sellers") or []:
                    co = s.get("commertialOffer") or {}
                    if not co.get("AvailableQuantity") or not co.get("Price"):
                        continue
                    spot = parse_price(co.get("spotPrice"))
                    price = spot if spot and spot <= co["Price"] else parse_price(co["Price"])
                    if best is None or price < best[0]:
                        imgs = it.get("images") or [{}]
                        best = (price, parse_price(co.get("ListPrice")), s.get("sellerName"), imgs[0].get("imageUrl"))
            if not best:
                continue
            seen.add(link)
            price, old, seller, img = best
            out.append(Offer(store=store, title=p.get("productName") or "", price=price, url=base + link,
                             old_price=old if old and old > price * 1.01 else None, image=img,
                             seller=seller, condition=condition_of(p.get("productName"))))
        if len(prods) < 50:
            break
    return out


def vtex_catalog(store: str, base: str, q: str) -> list[Offer]:
    """Lojas VTEX antigas: /api/catalog_system/pub/products/search (preço em sellers[].commertialOffer)."""
    r = http.get(f"{base}/api/catalog_system/pub/products/search", params={"ft": q, "_from": 0, "_to": 49}, json_api=True)
    out = []
    for p in r.json() or []:
        best = None
        for it in p.get("items") or []:
            for s in it.get("sellers") or []:
                co = s.get("commertialOffer") or {}
                if not co.get("AvailableQuantity") or not co.get("Price"):
                    continue
                price = parse_price(co["Price"])
                if price and (best is None or price < best[0]):
                    imgs = it.get("images") or [{}]
                    best = (price, parse_price(co.get("ListPrice")), s.get("sellerName"), imgs[0].get("imageUrl"))
        link = p.get("link") or (f"{base}/{p['linkText']}/p" if p.get("linkText") else None)
        if not (best and link):
            continue
        price, old, seller, img = best
        out.append(Offer(store=store, title=p.get("productName") or "", price=price,
                         url=link if link.startswith("http") else base + link,
                         old_price=old if old and old > price * 1.01 else None, image=img, seller=seller,
                         condition=condition_of(p.get("productName"))))
    return out


def vtex(store: str, base: str):
    """Coletor genérico para lojas VTEX: busca inteligente e, se não existir, o catálogo antigo."""
    def fn(q: str) -> list[Offer]:
        try:
            return vtex_search(store, base, q)
        except http.Blocked:
            raise
        except Exception:  # noqa: BLE001 - loja sem a busca inteligente
            return vtex_catalog(store, base, q)
    fn.__name__ = f"vtex_{slug(store)}"
    return fn


# ------------------------------------------------------------------ Amazon
def amazon(q: str) -> list[Offer]:
    html = http.get(f"https://www.amazon.com.br/s?k={quote_plus(q)}").text
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for c in soup.select('div[data-component-type="s-search-result"]'):
        t = c.select_one("h2 span") or c.select_one("h2")
        a = c.select_one("a.a-link-normal[href*='/dp/']") or c.select_one("h2 a")
        p = c.select_one("span.a-price:not(.a-text-price) span.a-offscreen")
        if not (t and a and p):
            continue
        old = c.select_one("span.a-price.a-text-price span.a-offscreen")
        img = c.select_one("img.s-image")
        href = a["href"]
        asin = c.get("data-asin")
        url = f"https://www.amazon.com.br/dp/{asin}" if asin else ("https://www.amazon.com.br" + href if href.startswith("/") else href)
        price = parse_price(p.get_text(strip=True))
        if price:
            out.append(Offer(store="Amazon", title=t.get_text(" ", strip=True), price=price, url=url,
                             old_price=parse_price(old.get_text(strip=True)) if old else None,
                             image=img.get("src") if img else None))
    return out


# ------------------------------------------------------------------ Shopee
def shopee(q: str) -> list[Offer]:
    r = http.get("https://shopee.com.br/api/v4/search/search_items",
                 params={"by": "relevancy", "keyword": q, "limit": 60, "newest": 0, "order": "desc",
                         "page_type": "search", "scenario": "PAGE_GLOBAL_SEARCH", "version": 2},
                 json_api=True, headers={"Referer": f"https://shopee.com.br/search?keyword={quote(q)}", "X-API-SOURCE": "pc"})
    data = r.json()
    if data.get("error") and not data.get("items"):
        raise http.Blocked("A Shopee exige login/verificação para buscas automáticas")
    out = []
    for it in data.get("items") or []:
        b = it.get("item_basic") or it
        price = (b.get("price_min") or b.get("price") or 0) / 100000
        if not price:
            continue
        old = (b.get("price_before_discount") or 0) / 100000
        out.append(Offer(store="Shopee", title=b.get("name", ""), price=price,
                         url=f"https://shopee.com.br/product/{b.get('shopid')}/{b.get('itemid')}",
                         old_price=old if old > price else None,
                         image=f"https://down-br.img.susercontent.com/file/{b['image']}" if b.get("image") else None,
                         seller=b.get("shop_location")))
    return out


# ------------------------------------------------------------------ AliExpress
def aliexpress(q: str) -> list[Offer]:
    html = http.get(f"https://pt.aliexpress.com/w/wholesale-{slug(q)}.html?sortType=total_tranpro_desc",
                    headers={"Cookie": "aep_usuc_f=site=bra&c_tp=BRL&region=BR&b_locale=pt_BR"}).text

    out, seen = [], set()
    for d in (x for b in all_blobs(html) for x in walk(b)):
        pid, prices = d.get("productId"), d.get("prices")
        if not (pid and isinstance(prices, dict)) or pid in seen:
            continue
        title = (d.get("title") or {}).get("displayTitle") if isinstance(d.get("title"), dict) else d.get("title")
        price = parse_price((prices.get("salePrice") or {}).get("minPrice"))
        if not (title and price):
            continue
        seen.add(pid)
        old = parse_price((prices.get("originalPrice") or {}).get("minPrice"))
        img = (d.get("image") or {}).get("imgUrl")
        out.append(Offer(store="AliExpress", title=title, price=price, url=f"https://pt.aliexpress.com/item/{pid}.html",
                         old_price=old if old and old > price else None,
                         image=("https:" + img) if img and img.startswith("//") else img,
                         condition=condition_of(title),
                         note="Importado: confira prazo, impostos (Remessa Conforme) e reputação do vendedor"))
    if out:
        return out

    def build(d):
        pid = d.get("productId") or d.get("itemId")
        return f"https://pt.aliexpress.com/item/{pid}.html" if pid else None
    offers = offers_from_json(all_blobs(html), "AliExpress", "https://pt.aliexpress.com/", url_builder=build)
    for o in offers:
        o.note = "Importado: confira prazo e impostos (Remessa Conforme)"
    return offers


# ------------------------------------------------------------------ Comparador (várias lojas de uma vez)
def zoom(q: str) -> list[Offer]:
    html = http.get(f"https://www.zoom.com.br/search?q={quote_plus(q)}").text
    offers = offers_from_json(all_blobs(html), "Zoom", "https://www.zoom.com.br/")
    for o in offers:
        o.note = "Menor preço encontrado pelo comparador Zoom (abre a página com todas as lojas)"
    return offers


# ------------------------------------------------------------------ Comunidades de promoção (bugs de preço aparecem aqui primeiro)
def pelando(q: str) -> list[Offer]:
    html = http.get(f"https://www.pelando.com.br/busca/{slug(q)}").text
    blobs = all_blobs(html)
    out, seen = [], set()
    # Página em Astro: props.initialData.deals.deals[] = {slug, title, price, status, store{name}, createdAt, couponCode?}
    for d in (x for b in blobs for x in walk(b)):
        if not (d.get("slug") and d.get("title") and "status" in d and "price" in d) or d["slug"] in seen:
            continue
        seen.add(d["slug"])
        price = parse_price(d.get("price"))
        if not price or d.get("kind") == "discussion" or str(d.get("status")).lower() != "active":
            continue  # promoções encerradas não são preço atual
        st = d.get("store") if isinstance(d.get("store"), dict) else {}
        img = d.get("image") if isinstance(d.get("image"), str) else None
        out.append(Offer(store="Pelando", title=d["title"], price=price, url=f"https://www.pelando.com.br/d/{d['slug']}",
                         kind="promo", via=st.get("name"), posted_at=d.get("createdAt"),
                         coupon=d.get("couponCode") if isinstance(d.get("couponCode"), str) else None,
                         image=img, condition=condition_of(d["title"])))
    if out or seen:
        return out

    def build(d):
        if d.get("__typename") in ("Offer", "Deal") or "sourceUrl" in d:
            s = d.get("slug") or d.get("id")
            return f"https://www.pelando.com.br/d/{s}" if s else None
        return None
    offers = offers_from_json(all_blobs(html), "Pelando", "https://www.pelando.com.br/", url_builder=build, kind="promo")
    if not offers:
        offers = offers_from_html(html, "Pelando", "https://www.pelando.com.br/", r"/d/", kind="promo")
    _promo_meta(offers, all_blobs(html))
    return offers


def promobit(q: str) -> list[Offer]:
    # A página /buscar é montada no navegador; os dados vêm desta API pública
    r = http.get("https://api.promobit.com.br/search/result/offers",
                 params={"q": q, "offer_status_name": "APPROVED", "sort": "lowest_price"}, json_api=True,
                 headers={"Origin": "https://www.promobit.com.br", "Referer": "https://www.promobit.com.br/"})
    data = r.json()
    if isinstance(data, dict) and "offers" in data:
        out = []
        for d in data.get("offers") or []:
            price = parse_price(d.get("offer_price"))
            if not (price and d.get("offer_slug") and d.get("offer_title")):
                continue
            old = parse_price(d.get("offer_old_price"))
            photo = d.get("offer_photo")
            out.append(Offer(store="Promobit", title=d["offer_title"], price=price,
                             url=f"https://www.promobit.com.br/oferta/{d['offer_slug']}/", kind="promo",
                             old_price=old if old and old > price else None, via=d.get("store_name"),
                             coupon=d.get("offer_coupon") or None, posted_at=d.get("offer_published"),
                             image=("https://i.promobit.com.br" + photo) if photo and photo.startswith("/") else photo,
                             condition=condition_of(d["offer_title"])))
        return out
    html = http.get(f"https://www.promobit.com.br/buscar/?q={quote_plus(q)}").text

    def build(d):
        s = d.get("offerSlug")
        return f"https://www.promobit.com.br/oferta/{s}/" if s else None
    offers = offers_from_json(all_blobs(html), "Promobit", "https://www.promobit.com.br/", url_builder=build, kind="promo")
    if not offers:
        offers = offers_from_html(html, "Promobit", "https://www.promobit.com.br/", r"/oferta/", kind="promo")
    _promo_meta(offers, all_blobs(html))
    return offers


def _promo_meta(offers: list[Offer], blobs: list) -> None:
    """Completa loja de origem, cupom e data das postagens das comunidades quando o JSON traz."""
    from .base import walk
    by_title = {o.title: o for o in offers}
    for blob in blobs:
        for d in walk(blob):
            t = d.get("title") or d.get("offerTitle") or d.get("name")
            o = by_title.get(t) if isinstance(t, str) else None
            if not o:
                continue
            st = d.get("store") or d.get("storeName") or d.get("retailer")
            if isinstance(st, dict):
                st = st.get("name")
            if isinstance(st, str):
                o.via = st
            cp = d.get("couponCode") or d.get("coupon") or d.get("offerCoupon")
            if isinstance(cp, dict):
                cp = cp.get("code")
            if isinstance(cp, str) and 2 < len(cp) < 40:
                o.coupon = cp
            stamps = d.get("timestamps") if isinstance(d.get("timestamps"), dict) else {}
            ts = d.get("createdAt") or d.get("publishedAt") or d.get("offerPublished") or stamps.get("createdAt")
            if isinstance(ts, str):
                o.posted_at = ts
            status = d.get("status") or d.get("offerStatus")
            if isinstance(status, str) and status.lower() in ("expired", "finished", "encerrada", "expirada"):
                o.note = "Promoção marcada como encerrada"


# id, nome, função, tipo, observação
STORES = [
    ("mercadolivre", "Mercado Livre", mercadolivre, "loja", ""),
    ("kabum", "KaBuM!", kabum, "loja", ""),
    ("pichau", "Pichau", pichau, "loja", ""),
    ("terabyte", "Terabyte", terabyte, "loja", ""),
    ("magalu", "Magalu", magalu, "loja", ""),
    ("amazon", "Amazon", amazon, "loja", ""),
    ("americanas", "Americanas", americanas, "loja", ""),
    ("carrefour", "Carrefour", vtex("Carrefour", "https://www.carrefour.com.br"), "loja", "VTEX"),
    ("ibyte", "Ibyte", vtex("Ibyte", "https://www.ibyte.com.br"), "loja", "VTEX"),
    ("shopee", "Shopee", shopee, "loja", "Costuma bloquear consultas automáticas"),
    ("aliexpress", "AliExpress", aliexpress, "loja", "Importado"),
    ("zoom", "Zoom (comparador)", zoom, "comparador", "Agrega dezenas de lojas"),
    ("pelando", "Pelando", pelando, "promo", "Comunidade: bugs de preço aparecem aqui primeiro"),
    ("promobit", "Promobit", promobit, "promo", "Comunidade de promoções"),
]


# Lojas avaliadas em nov/2026 e deixadas de fora (aparecem desligadas na tela Lojas e coleta)
OFF_STORES = [
    ("fastshop", "Fast Shop", "Responde 503 a consultas automáticas (proteção anti-robô)"),
    ("casasbahia", "Casas Bahia", "Responde 403: bloqueia consultas automáticas"),
    ("pontofrio", "Ponto", "Responde 403: bloqueia consultas automáticas"),
    ("kalunga", "Kalunga", "Não é VTEX e a busca é montada por JavaScript; nenhum produto legível na página"),
    ("patoloco", "Patoloco", "Não é VTEX e a busca é montada por JavaScript; nenhum produto legível na página"),
    ("gigantec", "Gigantec", "Página de busca vazia sem JavaScript"),
    ("megamamute", "Mega Mamute", "A busca redireciona para uma página de erro"),
    ("inpower", "Inpower", "Sem API de busca pública e página montada por JavaScript"),
    ("girafa", "Girafa", "Domínio não encontrado (loja fora do ar)"),
    ("submarino", "Submarino", "Domínio não encontrado (marca incorporada à Americanas)"),
]
