import json

from app.matching import norm, parse_price, reference_price, relevance
from app.stores.base import offers_from_html, offers_from_json, all_blobs
from app.coupons import discount_of, _from_page


def test_parse_price():
    assert parse_price("R$ 2.229,99") == 2229.99
    assert parse_price("2229.99") == 2229.99
    assert parse_price(2229) == 2229.0
    assert parse_price({"bestPrice": "1999.90"}) == 1999.9
    assert parse_price("R$\xa01.599") == 1599.0
    assert parse_price("") is None


def test_norm_and_relevance():
    assert norm("RTX3060 12 GB") == "rtx 3060 12gb"
    q = "RTX 3060 12GB"
    assert relevance(q, "Placa de Vídeo Mancer GeForce RTX 3060 Heimdall V2, 12GB GDDR6")[0]
    assert not relevance(q, "Placa de Vídeo RTX 3060 Ti 8GB")[0]
    assert not relevance(q, "Placa de vídeo RTX 3060 Ti 12GB")[0]
    assert not relevance(q, "RTX 3060 8GB Galax")[0]
    assert not relevance(q, "PC Gamer Ryzen 5 RTX 3060 12GB 16GB RAM")[0]
    assert not relevance(q, "Suporte para placa de vídeo RTX 3060 12GB")[0]
    assert relevance("rtx 3060 ti", "Placa RTX 3060 Ti 8GB")[0]
    assert not relevance(q, "Placa RTX 3060 12GB Gigabyte", exclude=["gigabyte"])[0]


def test_reference_price():
    assert reference_price([2200, 2300, 2400, 2600, 50]) == 2350
    assert reference_price([1, 2]) is None


def test_json_extraction():
    nd = {"props": {"pageProps": {"data": {"search": {"products": [
        {"title": "Placa de Vídeo RTX 3060 12GB Asus", "price": {"bestPrice": "2399.90", "fullPrice": "2999.00"},
         "path": "placa-rtx/p/abc123/", "image": "https://img/{w}x{h}/a.jpg"},
        {"title": "Categoria", "url": "/x"}]}}}}}
    html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(nd)}</script>'
    offs = offers_from_json(all_blobs(html), "Magalu", "https://www.magazineluiza.com.br/")
    assert len(offs) == 1
    o = offs[0]
    assert o.price == 2399.9 and o.old_price == 2999.0
    assert o.url == "https://www.magazineluiza.com.br/placa-rtx/p/abc123/"


def test_json_string_nested_and_pichau():
    inner = {"products": [{"name": "Placa de Video Mancer RTX 3060 12GB", "url_key": "placa-mancer-3060",
                           "pichau_prices": {"avista": 2229.99, "final_price": 2623.56}}]}
    html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps({"props": {"pageProps": {"data": json.dumps(inner)}}}) + "</script>"
    offs = offers_from_json(all_blobs(html), "Pichau", "https://www.pichau.com.br/",
                            url_builder=lambda d: "https://www.pichau.com.br/" + d["url_key"] if d.get("url_key") else None)
    assert offs and offs[0].price == 2229.99


def test_html_fallback_ignores_installment():
    html = """<div class="card"><a href="/produto/123/placa">Placa de Vídeo RTX 3060 12GB Inno3D</a>
      <span>R$ 3.705,84</span><span>R$ 3.149,99 à vista</span><span>12x de R$ 308,82</span></div>"""
    offs = offers_from_html(html, "Terabyte", "https://www.terabyteshop.com.br/", r"/produto/\d+")
    assert offs[0].price == 3149.99 and offs[0].old_price == 3705.84


def test_coupons():
    assert discount_of("13% OFF em placas de vídeo") == (13.0, None, None)
    assert discount_of("R$ 100 OFF em compras acima de R$ 1.500")[1:] == (100.0, 1500.0)
    html = '<div><p>Cupom 10% OFF em hardware acima de R$ 500</p><button data-code="HARD10">copiar</button></div>'
    cps = _from_page("KaBuM!", "X", "https://x", html)
    assert cps[0].code == "HARD10" and cps[0].pct == 10
