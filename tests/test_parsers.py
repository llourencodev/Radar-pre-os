"""Testes dos leitores de páginas reais (formatos encontrados em nov/2026), com HTML mínimo de exemplo."""
import html as _html
import json

import pytest

from app import http
from app.coupons import _from_page
from app.matching import relevance
from app.stores import catalog
from app.stores.base import all_blobs, astro_props, next_flight


def _flight(payload: str) -> str:
    return f"<script>self.__next_f.push([1,{json.dumps(payload)}])</script>"


def test_next_flight_reads_app_router_rows():
    row = {"products": {"items": [{"name": "Placa RTX 3060 12GB", "url_key": "placa-rtx",
                                   "pichau_prices": {"avista": 2199.99, "base_price": 3294.11}}]}}
    html = _flight('0:["$","div",null,{}]\n<!-- aviso -->20:["$","$L4d",null,' + json.dumps(row) + "]\n")
    blobs = next_flight(html)
    assert any("placa-rtx" in json.dumps(b) for b in blobs)
    assert any("placa-rtx" in json.dumps(b) for b in all_blobs(html))


def test_pichau_uses_pix_price_and_skips_out_of_stock(monkeypatch):
    items = [
        {"name": "Placa de Video Maxsun GeForce RTX 3060, 12GB", "url_key": "maxsun-3060", "stock_status": "IN_STOCK",
         "pichau_prices": {"avista": 2199.99, "avista_method": "PIX", "base_price": 3294.11, "final_price": 2588.22,
                           "max_installments": 12, "min_installment_price": 215.69},
         "image": {"url_listing": "https://img/x.jpg"}},
        {"name": "Placa de Video Asus RTX 3060 12GB", "url_key": "asus-3060", "stock_status": "OUT_OF_STOCK",
         "pichau_prices": {"avista": 1999.0}},
    ]
    html = _flight("5:" + json.dumps({"products": {"items": items}}) + "\n")

    class R:
        text = html
    monkeypatch.setattr(http, "get", lambda *a, **k: R())
    offs = catalog.pichau("rtx 3060 12gb", pages=1)
    assert len(offs) == 1
    o = offs[0]
    assert o.price == 2199.99 and o.old_price == 3294.11  # nunca a parcela de R$ 215,69
    assert o.url == "https://www.pichau.com.br/maxsun-3060" and o.installments.startswith("12x de R$ 215,69")


def test_astro_props_pelando_skips_expired(monkeypatch):
    props = {"initialData": [0, {"deals": [0, {"deals": [1, [
        [0, {"slug": [0, "rtx-ativa"], "title": [0, "Placa RTX 3060 12GB Zotac"], "price": [0, 1799],
             "status": [0, "active"], "kind": [0, "promotion"], "store": [0, {"name": [0, "KaBuM!"]}]}],
        [0, {"slug": [0, "rtx-velha"], "title": [0, "Placa RTX 3060 12GB Inno3D"], "price": [0, 1599],
             "status": [0, "expired"], "kind": [0, "promotion"]}],
    ]]}]}]}
    html = f'<astro-island uid="1" component-export="SearchFeedContent" props="{_html.escape(json.dumps(props))}"></astro-island>'
    assert astro_props(html)[0]["initialData"]["deals"]["deals"][0]["slug"] == "rtx-ativa"

    class R:
        text = html
    monkeypatch.setattr(http, "get", lambda *a, **k: R())
    offs = catalog.pelando("rtx 3060 12gb")
    assert [(o.price, o.via, o.url) for o in offs] == [(1799.0, "KaBuM!", "https://www.pelando.com.br/d/rtx-ativa")]


def test_vtex_picks_available_seller_and_spot_price(monkeypatch):
    data = {"products": [{"productName": "Placa de Vídeo Palit GeForce RTX 3060 12GB", "link": "/palit-3060/p",
                          "items": [{"images": [{"imageUrl": "https://img/p.jpg"}], "sellers": [
                              {"sellerName": "Loja A", "commertialOffer": {"AvailableQuantity": 0, "Price": 0}},
                              {"sellerName": "Magazine Luiza", "commertialOffer": {
                                  "AvailableQuantity": 10, "Price": 8729.9, "ListPrice": 9000, "spotPrice": 8293.4}}]}]}]}

    class R:
        def json(self):
            return data
    monkeypatch.setattr(http, "get", lambda *a, **k: R())
    offs = catalog.vtex_search("Americanas", "https://www.americanas.com.br", "rtx 3060", pages=1)
    assert len(offs) == 1
    assert offs[0].price == 8293.4 and offs[0].seller == "Magazine Luiza" and offs[0].old_price == 9000
    assert offs[0].url == "https://www.americanas.com.br/palit-3060/p"


def test_aliexpress_init_data_and_used_condition(monkeypatch):
    data = {"itemList": {"content": [
        {"productId": "100500", "title": {"displayTitle": "Placa Gráfica Usada RTX 3060 GAMING X 12GB"},
         "prices": {"salePrice": {"minPrice": 1500.5}, "originalPrice": {"minPrice": 2000}},
         "image": {"imgUrl": "//ae-pic/x.jpg"}}]}}
    html = "<script>window._dida_config_._init_data_= { data: " + json.dumps(data) + " }</script>"

    class R:
        text = html
    monkeypatch.setattr(http, "get", lambda *a, **k: R())
    o = catalog.aliexpress("rtx 3060 12gb")[0]
    assert (o.price, o.old_price, o.condition) == (1500.5, 2000.0, "usado")
    assert o.url == "https://pt.aliexpress.com/item/100500.html" and o.image == "https://ae-pic/x.jpg"


@pytest.mark.parametrize("page", [
    '<html data-assets-prefix="https://x/suspicious-traffic-frontend/"></html>',
    "<html><meta http-equiv=\"refresh\" content=\"5; URL='/s?k=x&bm-verify=AAQ'\"></html>",
])
def test_antibot_pages_are_reported_as_blocked(monkeypatch, page):
    class Resp:
        status_code = 200
        text = page

        def raise_for_status(self):
            pass

    class C:
        def get(self, *a, **k):
            return Resp()
    monkeypatch.setattr(http, "client", lambda: C())
    monkeypatch.setattr(http, "_throttle", lambda url: None)
    with pytest.raises(http.Blocked):
        http.get("https://lista.mercadolivre.com.br/x")


def test_relevance_drops_assembled_pcs():
    q = "rtx 3060 12gb"
    assert not relevance(q, "C Gamer Skill Aquarium Intel Core I5 10400F 16GB Geforce RTX 3060 12GB SSD 512GB")[0]
    assert not relevance(q, "Cpu Gamer Intel I9 11ª 16gb Ram 1Tb Placa de video Rtx 3060 12gb")[0]
    assert relevance(q, "Placa de Vídeo Gigabyte GeForce RTX 3060 Windforce OC, 12GB GDDR6")[0]


def test_coupon_cards_cuponomia_meliuz_pelando():
    cuponomia = """<ul><li data-type="code"><span class="js-couponSmallText">13% OFF</span>
      <h3 class="js-itemTitle">Placas de vídeo com cupom KaBuM!</h3><div class="item-desc">Válido até 30/11 no app.</div>
      <span class="js-itemCode">ZAFADINHO13</span></li></ul>"""
    c = _from_page("KaBuM!", "Cuponomia", "https://c", cuponomia)[0]
    assert (c.code, c.pct, c.expires) == ("ZAFADINHO13", 13.0, "30/11")
    assert c.title.startswith("13% OFF: Placas de vídeo") and "Válido até 30/11" in c.title

    meliuz = """<div class="cpn-layout offer-cpn" data-offer-code="TONOKABUM" data-offer-url="https://m/r/1"
      data-offer-title="Cupom KaBuM! com 5% OFF na primeira compra"><span>5%</span><span>TONOKABUM</span>
      <p>Válido na primeira compra acima de R$499.</p></div>"""
    c = _from_page("KaBuM!", "Méliuz", "https://m", meliuz)[0]
    assert (c.code, c.pct, c.min_value, c.url) == ("TONOKABUM", 5.0, 499.0, "https://m/r/1")

    pelando = """<article class="card"><h3>Cupom Amazon oferece R$ 25 OFF em R$ 80</h3>
      <a href="/d/cupom-amazon-25">ver</a><button data-copy-code="BLACK25PRIME">Copiar</button></article>"""
    c = _from_page("Amazon", "Pelando", "https://p", pelando)[0]
    assert (c.code, c.url) == ("BLACK25PRIME", "https://www.pelando.com.br/d/cupom-amazon-25")


def test_vtex_catalog_legacy_api(monkeypatch):
    data = [{"productName": "Placa de Vídeo RTX 3060 12GB Zotac", "link": "https://loja.com.br/rtx-3060-zotac/p",
             "items": [{"images": [{"imageUrl": "https://img/z.jpg"}], "sellers": [
                 {"sellerName": "X", "commertialOffer": {"AvailableQuantity": 0, "Price": 100}},
                 {"sellerName": "Loja", "commertialOffer": {"AvailableQuantity": 3, "Price": 2499.9, "ListPrice": 2999.9}}]}]},
            {"productName": "Sem estoque RTX 3060 12GB", "link": "/x/p",
             "items": [{"sellers": [{"commertialOffer": {"AvailableQuantity": 0, "Price": 1}}]}]}]

    class R:
        def json(self):
            return data
    monkeypatch.setattr(http, "get", lambda *a, **k: R())
    offs = catalog.vtex_catalog("Loja", "https://loja.com.br", "rtx 3060 12gb")
    assert [(o.price, o.old_price, o.seller) for o in offs] == [(2499.9, 2999.9, "Loja")]
