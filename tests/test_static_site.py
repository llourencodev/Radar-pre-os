"""Versão estática (GitHub Pages): JSON com o que as telas usam e nada privado."""
import json

import pytest

from app import config, db, static_site


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "_conn", None)
    # segredos configurados não podem aparecer no site
    monkeypatch.setattr(config, "TELEGRAM_TOKEN", "123456:SEGREDO-TELEGRAM")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "999888777")
    monkeypatch.setattr(config, "ML_ACCESS_TOKEN", "APP_USR-SEGREDO-ML")
    db.init_db()
    w = db.upsert_watch("RTX 3060 12GB")
    other = db.upsert_watch("Produto fora do site")
    for i, (store, price) in enumerate([("KaBuM!", 2199.99), ("Pichau", 2299.0), ("Terabyte", 2399.0), ("Amazon", 2499.0)]):
        oid = db.run("INSERT INTO offers(watch_id, store, title, url, price, kind, condition, first_seen, last_seen, active, first_run)"
                     " VALUES (?,?,?,?,?,?,?,?,?,1,1)",
                     (w["id"], store, f"Placa de Vídeo RTX 3060 12GB modelo {i}", f"https://loja/{i}", price, "produto", "novo",
                      db.now(), db.now()))
        db.run("INSERT INTO history VALUES (?,?,?)", (oid, price, db.now()))
    db.run("INSERT INTO offers(watch_id, store, title, url, price, kind, first_seen, last_seen, active) VALUES (?,?,?,?,?,?,?,?,1)",
           (other["id"], "KaBuM!", "Outro", "https://loja/x", 10.0, "produto", db.now(), db.now()))
    yield w, other, tmp_path
    db.conn().close()
    monkeypatch.setattr(db, "_conn", None)


def test_export_has_everything_the_pages_use(setup):
    w, other, tmp = setup
    info = static_site.export(tmp / "site", [w["id"]], 60)
    site = tmp / "site"
    html = (site / "index.html").read_text(encoding="utf-8")
    assert 'src="static-api.js"' in html and 'href="styles.css"' in html and "Content-Security-Policy" in html
    assert "/static/" not in html
    for f in ("app.js", "styles.css", "static-api.js", ".nojekyll", "data/status.json", "data/historico.json"):
        assert (site / f).exists(), f
    data = json.loads((site / "data" / "precos.json").read_text(encoding="utf-8"))
    for k in ("generated_at", "meta", "status", "dashboard", "watches", "details", "coupons", "stores"):
        assert k in data, k
    assert data["status"]["static"] and data["status"]["generated_at"] == data["generated_at"]
    assert [x["query"] for x in data["watches"]] == ["RTX 3060 12GB"]          # só os produtos de config/produtos.json
    d = data["details"][str(w["id"])]
    assert len(d["items"]) == 4 and d["ref_price"] and {"flags", "ratio", "history", "coupons"} <= set(d) | set(d["items"][0])
    assert all(o["watch_id"] == w["id"] for o in data["dashboard"]["hot"] + data["dashboard"]["new"])
    assert info["offers"] == 4
    hist = json.loads((site / "data" / "historico.json").read_text(encoding="utf-8"))
    assert hist[str(d["items"][0]["id"])][0]["price"] == d["items"][0]["price"]


def test_export_has_no_secrets_or_local_paths(setup):
    w, _other, tmp = setup
    static_site.export(tmp / "site", [w["id"]], 60)
    text = "".join(p.read_text(encoding="utf-8") for p in (tmp / "site" / "data").glob("*.json"))
    paths = [str(config.BASE_DIR), str(tmp)]
    for secret in ("SEGREDO-TELEGRAM", "999888777", "APP_USR-SEGREDO-ML", *paths, *(json.dumps(p)[1:-1] for p in paths)):
        assert secret not in text, secret
    data = json.loads((tmp / "site" / "data" / "precos.json").read_text(encoding="utf-8"))
    assert data["status"]["telegram"] is False


def test_export_includes_search_api_in_csp_and_meta(setup, monkeypatch):
    w, _other, tmp = setup
    monkeypatch.setenv("PRECOS_API_URL", "https://radar-precos-api.onrender.com/")
    static_site.export(tmp / "site", [w["id"]], 60)
    html = (tmp / "site" / "index.html").read_text(encoding="utf-8")
    assert "connect-src 'self' https://radar-precos-api.onrender.com;" in html
    data = json.loads((tmp / "site" / "data" / "precos.json").read_text(encoding="utf-8"))
    assert data["meta"]["api_url"] == "https://radar-precos-api.onrender.com"


@pytest.mark.parametrize("url", ["http://evil.example", "javascript:alert(1)", "https://x.com/a b", "https://x.com'; script-src *"])
def test_export_rejects_bad_api_url(setup, monkeypatch, url):
    w, _other, tmp = setup
    monkeypatch.setenv("PRECOS_API_URL", url)
    with pytest.raises(ValueError):
        static_site.export(tmp / "site", [w["id"]], 60)
