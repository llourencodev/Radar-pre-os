"""Busca pedida pelo site publicado: o título de uma issue "Buscar: <produto>" vira um produto em config/produtos.json.

Usado pelo workflow .github/workflows/busca.yml. O título da issue é texto digitado por alguém e é tratado como
dado não confiável: só letras, números, espaço e - . + / passam, com no máximo 80 caracteres.

Uso:  python -m app.busca            (lê o título da variável de ambiente ISSUE_TITLE)
Saída (para o GitHub Actions): query=<produto>, added=true|false, slug=<id do produto no site, se já existir>
"""
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

PREFIX = re.compile(r"^\s*buscar\s*:\s*", re.I)
MAX_LEN = 80
_ALLOWED = re.compile(r"[^\w\s\-.+/]|_", re.UNICODE)


def sanitize(title: str) -> str | None:
    """'Buscar: Monitor Portátil 15"' -> 'Monitor Portátil 15'. None se não for um pedido válido."""
    if not isinstance(title, str) or not PREFIX.match(title):
        return None
    q = PREFIX.sub("", title, count=1)
    q = unicodedata.normalize("NFC", q)
    q = _ALLOWED.sub(" ", q)
    q = " ".join(q.split())[:MAX_LEN].strip()
    return q if len(re.sub(r"[\s\-.+/]", "", q)) >= 2 else None


def _key(q: str) -> str:
    q = unicodedata.normalize("NFKD", q.lower())
    return " ".join("".join(c for c in q if not unicodedata.combining(c)).split())


def add_product(path: Path, query: str) -> bool:
    """Acrescenta o produto em config/produtos.json. False se já existir (mesmo nome, sem diferenciar acentos/caixa)."""
    path = Path(path)
    items = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    if any(_key(str(it.get("query", ""))) == _key(query) for it in items):
        return False
    items.append({"query": query, "exclude": "", "target_price": None})
    body = ",\n".join("  " + json.dumps(it, ensure_ascii=False) for it in items)
    path.write_text(f"[\n{body}\n]\n", encoding="utf-8")
    return True


def main() -> int:
    q = sanitize(os.environ.get("ISSUE_TITLE", ""))
    if not q:
        print("Título inválido: use 'Buscar: nome do produto' (letras, números, espaço e - . + /)", file=sys.stderr)
        return 1
    added = add_product(Path(__file__).resolve().parent.parent / "config" / "produtos.json", q)
    out = os.environ.get("GITHUB_OUTPUT")
    lines = [f"query={q}", f"added={'true' if added else 'false'}"]
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
