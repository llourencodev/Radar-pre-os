"""Busca instantânea (/api/buscar): relevância, selos, cache, limite por IP, tempo esgotado, CORS e modo api."""
import time

import pytest
from fastapi.testclient import TestClient

from app import collector, config, db, instant
from app import main as server
from app.stores.base import Offer

CALLS = {"n": 0}


def _store(name, offers, delay=0.0):
    def fn(q):
        CALLS["n"] += 1
        if delay:
            time.sleep(delay)
        return [Offer(store=name, title=t, price=p, url=f"https://{name}/{i}") for i, (t, p) in enumerate(offers)]
    return (name.lower(), name, fn, "loja", "")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "_conn", None)
    db.init_db()
    db.run("INSERT INTO coupon_runs VALUES (?,?,?,?,?)", ("KaBuM!", "ok", None, 1, db.now()))  # cupons em dia
    db.run("INSERT INTO coupons(store, code, title, url, source, pct, first_seen, last_seen) VALUES (?,?,?,?,?,?,?,?)",
           ("KaBuM!", "HARD10", "10% OFF em monitores", "https://x", "Teste", 10, db.now(), db.now()))
    db.run("INSERT INTO coupons(store, code, title, url, source, pct, first_seen, last_seen) VALUES (?,?,?,?,?,?,?,?)",
           ("Shopee", "SHOP5", "5% OFF", "https://x", "Teste", 5, db.now(), db.now()))
    stores = [
        _store("KaBuM!", [("Monitor Portátil 15.6 Full HD USB-C", 899.0), ("Capa para Monitor Portátil 15.6", 49.0)]),
        _store("Pichau", [("Monitor Portatil 16 Polegadas IPS", 950.0), ("Monitor Portátil 15.6 2K", 1000.0)]),
        _store("Terabyte", [("Monitor Portátil 14 Polegadas", 420.0), ("Monitor Portátil 15 Touch", 1050.0)]),
        _store("Lenta", [("Monitor Portátil 15.6", 10.0)], delay=3),
    ]
    monkeypatch.setattr(collector, "enabled_stores", lambda: stores)
    monkeypatch.setattr(config, "SEARCH_TIMEOUT", 1)
    monkeypatch.setattr(instant, "limiter", instant.RateLimiter(5))
    monkeypatch.setattr(instant, "_cache", {})
    CALLS["n"] = 0
    yield TestClient(server.app)
    db.conn().close()
    monkeypatch.setattr(db, "_conn", None)


def test_search_filters_flags_and_store_status(client):
    r = client.get("/api/buscar", params={"q": "monitor portatil"})
    assert r.status_code == 200
    d = r.json()
    titles = [o["title"] for o in d["items"]]
    assert "Capa para Monitor Portátil 15.6" not in titles                  # acessório fora
    assert [o["price"] for o in d["items"]] == sorted(o["price"] for o in d["items"])
    assert d["ref_price"] == 950.0 and d["best"]["price"] == 420.0
    cheap = next(o for o in d["items"] if o["price"] == 420.0)
    assert "bugao" in cheap["flags"]                                        # 44% da referência
    assert all(o["id"] < 0 for o in d["items"])                             # sem histórico guardado
    st = {s["store"]: s for s in d["stores"]}
    assert st["Lenta"]["status"] == "tempo esgotado" and st["KaBuM!"]["matched"] == 1
    assert [c["code"] for c in d["coupons"]] == ["HARD10"]                  # só lojas presentes
    assert d["cached"] is False


def test_cache_by_normalized_term(client):
    client.get("/api/buscar", params={"q": "Monitor Portátil"})
    n = CALLS["n"]
    d = client.get("/api/buscar", params={"q": "  monitor   portatil "}).json()
    assert d["cached"] is True and CALLS["n"] == n


def test_rate_limit_per_ip(client):
    codes = [client.get("/api/buscar", params={"q": "monitor portatil"}).status_code for _ in range(6)]
    assert codes[:5] == [200] * 5 and codes[5] == 429


@pytest.mark.parametrize("q", ["", "a", "x" * 81, "  ", "!!"])
def test_term_length(client, q):
    assert client.get("/api/buscar", params={"q": q}).status_code == 422


def test_cors_only_for_the_site(client):
    ok = client.get("/api/saude", headers={"Origin": "https://llourencodev.github.io"})
    assert ok.headers.get("access-control-allow-origin") == "https://llourencodev.github.io"
    bad = client.get("/api/saude", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in bad.headers
    pre = client.options("/api/buscar", headers={"Origin": "http://localhost:8010", "Access-Control-Request-Method": "GET"})
    assert pre.status_code == 200 and pre.headers["access-control-allow-origin"] == "http://localhost:8010"


def test_api_mode_exposes_only_search(client, monkeypatch):
    monkeypatch.setattr(config, "API_MODE", True)
    assert client.get("/api/saude").json()["ok"] is True
    assert client.get("/api/buscar", params={"q": "monitor portatil"}).status_code == 200
    assert client.get("/api/watches").status_code == 404
    assert client.post("/api/search", json={"q": "ps5"}).status_code == 404
    assert client.get("/").status_code == 404
