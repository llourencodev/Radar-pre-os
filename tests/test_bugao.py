"""Selo BUGÃO, referência só com lojas brasileiras e cupom com valor mal escrito."""
import pytest

from app import config, db
from app.coupons import discount_of


@pytest.fixture
def watch(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "_conn", None)
    db.init_db()
    w = db.upsert_watch("RTX 3060 12GB")
    yield w
    db.conn().close()
    monkeypatch.setattr(db, "_conn", None)


def _add(wid, store, price, url=None, kind="produto", condition="novo"):
    db.run("INSERT INTO offers(watch_id, store, title, url, price, kind, condition, first_seen, last_seen, active, first_run)"
           " VALUES (?,?,?,?,?,?,?,?,?,1,1)",
           (wid, store, "Placa RTX 3060 12GB", url or f"https://x/{store}/{price}", price, kind, condition, db.now(), db.now()))


def _flags(w):
    return {o["price"]: o["flags"] for o in db.annotated_offers(w)}


def _base(wid):
    for s, p in [("KaBuM!", 2000), ("Pichau", 2000), ("Terabyte", 2000), ("Magalu", 2000), ("Amazon", 2000)]:
        _add(wid, s, p)


def test_bugao_at_50_percent(watch):
    _base(watch["id"])
    _add(watch["id"], "Mercado Livre", 1000)   # 50% da referência
    _add(watch["id"], "Americanas", 1200)      # 60%: continua bug
    f = _flags(watch)
    assert "bugao" in f[1000] and "bug" not in f[1000] and "suspeito" not in f[1000]
    assert "bug" in f[1200] and "bugao" not in f[1200]
    st = db.get_watch(watch["id"])
    assert st["bugs"] == 2 and st["bugaos"] == 1


def test_bugao_at_90_percent_is_also_suspect(watch):
    _base(watch["id"])
    _add(watch["id"], "Shopee", 200)           # 90% de desconto
    _add(watch["id"], "Mercado Livre", 600)    # 70% de desconto
    f = _flags(watch)
    assert {"bugao", "suspeito"} <= set(f[200])
    assert "bugao" in f[600] and "suspeito" not in f[600]


def test_reference_ignores_aliexpress_zoom_promo_and_used(watch):
    wid = watch["id"]
    _add(wid, "KaBuM!", 2199)
    _add(wid, "Pichau", 2199)
    _add(wid, "Terabyte", 2299)
    for i, p in enumerate([1100, 1150, 1200, 1250, 1300, 1350]):
        _add(wid, "AliExpress", p, url=f"https://ali/{i}")
    _add(wid, "Zoom", 900)
    _add(wid, "Pelando", 800, kind="promo")
    _add(wid, "Mercado Livre", 700, condition="usado")
    offers = db.annotated_offers(watch)
    assert offers[0]["ref_price"] == 2199
    f = _flags(watch)
    assert not {"bug", "bugao"} & set(f[2199])  # KaBuM e Pichau a R$ 2.199 não são mais "bug"


def test_coupon_amount_malformed_or_too_high():
    assert discount_of("Desconto de R$ 3.290.84 em placas")[1] is None
    assert discount_of("R$ 2.500 OFF em notebooks")[1] is None
    assert discount_of("R$ 150 OFF em placas de vídeo")[1] == 150.0


def test_reference_ignores_overpriced_listings(watch):
    from app.matching import reference_price
    prices = [2199, 2199, 2299, 2599, 3099, 3099, 5390, 8293]
    assert reference_price(prices) == 2449  # sem 5390 e 8293 (acima de 1,6x a mediana)
    for i, p in enumerate(prices):
        _add(watch["id"], ["KaBuM!", "Pichau", "Amazon", "Terabyte"][i % 4], p, url=f"https://x/{i}")
    for o in db.annotated_offers(watch):
        if o["price"] == 2199:
            assert not {"bug", "bugao"} & set(o["flags"])
