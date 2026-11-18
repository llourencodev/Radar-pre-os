"""Filtro de relevância genérico: acessórios, termos inteiros e coerência de preço."""
import pytest

from app import config, db
from app.matching import relevance


@pytest.mark.parametrize("title", [
    "FACAO MATO COM CABO DE MADEIRA 16",
    "Capa para iPhone 16 Silicone",
    "Capinha Anti Impacto iPhone 16",
    "Película de Vidro Temperado iPhone 16",
    "Pelicula 3D p/ iPhone 16",
    "Cabo para iPhone 16 USB-C 2m",
    "Carregador 20W compatível com iPhone 16",
    "Kit Capinha + Película iPhone 16",
    "Suporte veicular compatível com iPhone 16",
    "Vidro traseiro para iPhone 16",
    "iPhone 160 qualquer coisa",
    "Réplica iPhone 16 não funcional",
])
def test_rejects_accessories_for_iphone_16(title):
    assert not relevance("iphone 16", title)[0], title


@pytest.mark.parametrize("title", [
    "Apple iPhone 16 (128 GB) - Preto",
    "iPhone 16 Apple 128GB, Câmera de 48MP, Chip A18, Tela 6.1\"",
    "Apple iPhone 16 128GB Preto (sem carregador)",
])
def test_accepts_real_iphone_16(title):
    assert relevance("iphone 16", title)[0], title


def test_accessory_word_in_query_is_allowed():
    assert relevance("capa iphone 16", "Capa para iPhone 16 Silicone")[0]


def test_console_bundles_vs_games():
    assert relevance("PS5", "Console PS5 Slim + Jogo GTA VI")[0]
    assert relevance("PS5", "Console PS5 Slim, 1 Controle DualSense")[0]
    assert not relevance("PS5", "Jogo GTA VI PS5")[0]
    assert not relevance("PS5", "Controle DualSense PS5 Branco")[0]
    assert not relevance("PS5", "Disco para Sony PS5 10.20 Jailbreak")[0]


@pytest.fixture
def watch(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "_conn", None)
    db.init_db()
    yield db.upsert_watch("iphone 16")
    db.conn().close()
    monkeypatch.setattr(db, "_conn", None)


def _add(wid, store, price, title, kind="produto"):
    db.run("INSERT INTO offers(watch_id, store, title, url, price, kind, condition, first_seen, last_seen, active, first_run)"
           " VALUES (?,?,?,?,?,?,?,?,?,1,1)", (wid, store, title, f"https://x/{store}/{price}/{title}", price, kind, "novo", db.now(), db.now()))


def test_prune_old_offers_and_price_coherence(watch):
    wid = watch["id"]
    for i, p in enumerate([5000, 5100, 5200, 5300]):
        _add(wid, "KaBuM!", p, f"Apple iPhone 16 128GB cor {i}")
    _add(wid, "Mercado Livre", 49.9, "FACAO MATO COM CABO DE MADEIRA 16")       # gravada antes do filtro novo
    _add(wid, "AliExpress", 59.9, "Capa para iPhone 16")                        # acessório
    _add(wid, "AliExpress", 300.0, "iPhone 16 modelo para vitrine")             # < 20% da referência e casamento fraco
    _add(wid, "Promobit", 0.01, "iPhone 16 com R$ 500 de desconto", kind="promo")  # preço simbólico
    _add(wid, "Amazon", 900.0, "Apple iPhone 16 128GB Preto")                   # < 20% mas casa muito bem: fica
    assert db.prune_offers(wid) == 4
    left = {o["title"] for o in db.annotated_offers(watch)}
    assert "Apple iPhone 16 128GB Preto" in left and len(left) == 5
    assert db.prune_offers(wid) == 0


def test_games_and_cheap_platform_items():
    from app.matching import strict_match
    assert not relevance("PS5", "Minecraft PS5 Midia Fisica - Playstation")[0]
    assert not relevance("PS5", "GTA 6 PS5 Code in Box Pré-venda")[0]
    assert not strict_match("PS5", "Sonic Frontiers PS5")
    assert strict_match("iphone 16", "Apple iPhone 16 128GB Preto")


def test_playstation_alias():
    assert relevance("PS5", "Console Sony PlayStation 5 Slim Edição Digital 825GB")[0]
    assert relevance("playstation 5", "Console PS5 Slim")[0]
    assert not relevance("PS5", "Console Sony PlayStation 4 Slim")[0]


def test_plural_and_vr():
    assert not relevance("PS5", "Tampas do console PlayStation 5 Slim - Midnight Black")[0]
    assert not relevance("PS5", "Sony PlayStation VR2 PS VR2 OLED 120fps")[0]
