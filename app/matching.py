"""Normalização de textos e preços e filtro de relevância (o anúncio é mesmo o produto buscado?)."""
import itertools
import re
import statistics
import unicodedata

# Palavras que indicam acessório, peça ou produto diferente do buscado (valem para qualquer produto,
# a não ser que a palavra esteja na própria busca).
ACCESSORY_WORDS = [
    # acessórios em geral
    "case", "capa", "capinha", "pelicula", "película", "vidro temperado", "protetor de tela", "carregador", "cabo",
    "fonte", "fone", "headset", "adaptador", "suporte", "bateria para", "tela para", "display para", "lente", "skin",
    "pulseira", "kit", "acessorio", "acessório", "acessorios", "acessórios", "adesivo", "controle", "base de carregamento",
    "base carregamento", "dock", "bolsa", "mochila", "estojo", "tampa", "faceplate", "painel lateral",
    # peças, réplicas e outros produtos
    "chip", "chipset", "placa mae", "placa-mãe", "flex", "conector", "botoes", "botões", "replica", "réplica",
    "telefone falso", "modelo falso", "dummy", "maquete", "modelo de exibicao", "modelo de exibição", "brinquedo",
    "jogo", "game", "midia fisica", "mídia física", "midia digital", "mídia digital", "code in box", "codigo digital",
    "código digital", "dualsense", "control", "volante", "cambio", "câmbio", "freio de mao", "freio de mão", "pedal",
    "pedaleira", "oculos", "óculos", "realidade virtual", "vr", "vr 2", "jailbreak", "disco de inicializacao", "disco de inicialização",
    "caixa vazia", "somente caixa", "so a caixa", "só a caixa", "manual", "defeito", "defeituosa",
    "para retirada de pecas", "retirada de peças", "sucata", "chaveiro", "miniatura", "camiseta", "poster", "pôster",
    "gift card", "consórcio",
    # aparelhos de saúde e de bebê que também se chamam "monitor"
    "frequencia cardiaca", "frequência cardíaca", "pressao arterial", "pressão arterial", "fetal", "doppler", "oximetro",
    "oxímetro", "glicose", "babá eletrônica", "baba eletronica", "monitor de bebe", "monitor de bebê",
    # placas de vídeo: peças e PCs montados que citam a placa no título
    "cooler para", "backplate", "riser", "extensor", "waterblock", "water block", "bracket", "fan para", "ventoinha",
    "parafuso", "pc gamer", "computador", "notebook", "desktop completo", "kit upgrade", "mini pc", "all in one",
    "ssd", "intel core", "ryzen", "c gamer", "cpu gamer",
]
# "sem carregador", "acompanha cabo"... descrevem o próprio produto, não são acessório
_INCLUDED = re.compile(r"\b(?:sem|com|acompanha|acompanham|inclui|incluso|inclusos|e)\s+(?:o\s+|a\s+)?(?:cabo|carregador|fone|fonte|capa|pelicula|case|controle|jogo)\b")
# "para iPhone", "p/ iPhone", "compatível com iPhone": o produto buscado só aparece como destino do acessório
_FOR = re.compile(r"\b(?:para|p|pra|compativel com|compativel|compatíveis com|compativeis com|compativeis|serve em|serve no)\s+((?:\w+\s+){0,3}?)")
# Palavras ambíguas: produtos de verdade também as citam DEPOIS do nome ("iPhone 18 ... Chip A20",
# "PS5 Slim + Jogo", "1 Controle", "cabo USB-C incluso"). Só indicam acessório quando vêm ANTES do produto.
WEAK_WORDS = {"chip", "controle", "control", "dualsense", "jogo", "game", "cabo", "carregador", "fone", "fonte", "kit", "adaptador", "headset", "lente",
              "dock", "manual", "flex", "conector", "bateria para", "tela para", "display para"}
_FOR_OK = {"pc", "jogos", "games", "gamer", "gaming", "computador", "desktop", "uso", "voce", "presente", "entrega"}
# Nomes equivalentes: o anúncio pode usar o nome completo e a busca a sigla (ou o contrário)
ALIASES = [("playstation 5", "ps 5"), ("playstation 4", "ps 4"), ("xbox series x", "xsx"), ("nintendo switch", "switch")]


def with_aliases(tn: str) -> str:
    """Acrescenta ao título normalizado as formas equivalentes ("playstation 5" também vale como "ps 5")."""
    extra = [b if a in f" {tn} " else a for a, b in ALIASES if f" {a} " in f" {tn} " or f" {b} " in f" {tn} "]
    return f"{tn} {' '.join(extra)}".strip() if extra else tn


VARIANT_SUFFIXES = ["ti", "super", "xt", "xtx", "max", "plus", "pro", "ultra", "mini", "lite"]

_PRICE_RE = re.compile(r"(?:R\$\s*)?(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?")


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm(s: str) -> str:
    s = strip_accents((s or "").lower())
    s = re.sub(r"(\d+)\s*(gb|tb|mb|hz|w)\b", r"\1\2", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    # separa letras de números ("rtx3060" -> "rtx 3060"), mantendo unidades ("12gb")
    s = re.sub(r"([a-z])(\d)", r"\1 \2", s)
    s = re.sub(r"(\d)(?!(?:gb|tb|mb|hz|w)\b)([a-z])", r"\1 \2", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(s: str) -> list[str]:
    return [t for t in norm(s).split() if t not in ("de", "da", "do", "e", "com", "para", "a", "o")]


def parse_price(v) -> float | None:
    """Converte 2229.99, "2229.99", "R$ 2.229,99", {"value": ...} em float."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return f if 0 < f < 10_000_000 else None
    if isinstance(v, dict):
        for k in ("value", "amount", "bestPrice", "best_price", "price", "current", "final", "pix"):
            if k in v:
                p = parse_price(v[k])
                if p:
                    return p
        return None
    s = str(v).strip()
    if not s:
        return None
    if re.fullmatch(r"\d+(\.\d{1,2})?", s):
        return parse_price(float(s))
    m = _PRICE_RE.search(s.replace("\xa0", " "))
    if not m:
        return None
    inteiro = m.group(1).replace(".", "")
    cents = m.group(2) or "0"
    try:
        return parse_price(float(f"{inteiro}.{cents}"))
    except ValueError:
        return None


def _words(s: str) -> str:
    return " " + " ".join(norm(s).split()) + " "


def _too_far(qt: list[str], words: list[str]) -> bool:
    """True se as palavras da busca (só letras, 3+ caracteres) não cabem numa janela de len+1 palavras do título."""
    key = [t for t in dict.fromkeys(qt) if t.isalpha() and len(t) >= 3]
    if len(key) < 2:
        return False
    pos = {t: [i for i, w in enumerate(words) if w == t] for t in key}
    if any(not p for p in pos.values()):
        return False  # termo veio por sinônimo (ex.: PlayStation 5 = PS5): sem como medir distância
    best = min(max(c) - min(c) + 1 for c in itertools.islice(itertools.product(*pos.values()), 500))
    return best > len(key) + 1


def relevance(query: str, title: str, exclude: list[str] | None = None) -> tuple[bool, str]:
    """True quando o título contém todos os termos da busca (palavras inteiras) e não parece acessório/variante."""
    qt = tokens(query)
    tn = with_aliases(norm(title))
    tt = set(tn.split())
    for t in qt:
        if t not in tt:  # palavras inteiras: "16" não casa com "160"
            return False, f"sem o termo '{t}'"
    # palavras da busca perto umas das outras: "monitor portátil" aceita "Monitor LED Portátil", mas não
    # "Monitor Fetal Doppler Portátil" nem "Monitor de Pressão ... Portátil". Números e siglas curtas
    # (3060, 12gb, 5) ficam livres, porque as lojas os põem em qualquer lugar do título.
    if _too_far(qt, [w for w in norm(title).split() if not any(c.isdigit() for c in w)]):
        return False, "termos da busca distantes no título"
    # variante diferente: busca "3060" não aceita "3060 ti" (a menos que a busca peça)
    for t in qt:
        if t.isdigit() and len(t) >= 3:
            m = re.search(rf"\b{t} ({'|'.join(VARIANT_SUFFIXES)})\b", tn)
            if m and m.group(1) not in qt:
                return False, f"variante {t} {m.group(1)}"
    qn = _words(query)
    clean = " " + _INCLUDED.sub(" ", tn) + " "
    main = next((t for t in qt if not t.isdigit()), qt[0] if qt else None)
    first_main = clean.find(f" {main} ") if main else -1
    for w in ACCESSORY_WORDS + [x for x in (exclude or []) if x.strip()]:
        wn = " ".join(norm(w).split())
        pos = min((clean.find(f" {x} ") for x in (wn, wn + "s") if wn and f" {x} " in clean), default=-1)  # aceita plural
        if pos < 0 or f" {wn} " in qn:
            continue
        if w in WEAK_WORDS and first_main >= 0 and pos > first_main:
            continue  # citado depois do nome do produto: é detalhe do próprio produto
        return False, f"parece '{w}'"
    # acessório "para <produto>": o termo principal da busca aparece primeiro logo depois de "para"/"compatível com"
    if main and " para " not in qn and " compativel " not in qn:
        first = re.search(rf"\b{re.escape(main)}\b", tn)
        if first:
            # "para"/"compatível com" antes da primeira menção ao produto, a no máximo 3 palavras dela
            for m in _FOR.finditer(tn[: first.start()]):
                between = tn[m.end(): first.start()].split()
                if len(between) <= 3 and not (between and between[0] in _FOR_OK):
                    return False, f"acessório para '{main}'"
    return True, ""


_LOOSE = re.compile(r"\b(?:para|p|pra|compativel|compativeis|replica|modelo|falso|similar|tipo|estilo)\b")


def strict_match(query: str, title: str) -> bool:
    """Casamento forte: passa no filtro e o título não tem nenhum indício de 'para X'/réplica/similar."""
    if not relevance(query, title)[0] or _LOOSE.search(norm(title)):
        return False
    # o produto precisa vir na primeira metade do título ("Sonic Frontiers PS5" é um jogo, não o console)
    tn, qn = f" {norm(title)} ", f" {norm(query)} "
    for a, b in ALIASES:  # escreve o título com a mesma forma usada na busca ("playstation 5" -> "ps 5")
        src, dst = (a, b) if f" {b} " in qn else (b, a)
        tn = tn.replace(f" {src} ", f" {dst} ")
    words = tn.split()
    qt = tokens(query)
    main = next((t for t in qt if not t.isdigit()), qt[0] if qt else "")
    return main in words and words.index(main) < max(2, len(words) / 2)


def reference_price(prices: list[float]) -> float | None:
    """Preço de referência = mediana das ofertas válidas (robusta a anúncios extremos)."""
    ps = sorted(p for p in prices if p)
    if len(ps) < 3:
        return None
    med = statistics.median(ps)
    # descarta extremos óbvios antes de recalcular
    # anúncios caros demais (kits, preços fora da realidade) inflavam a referência e criavam falsos bugs
    core = [p for p in ps if med * 0.4 <= p <= med * 1.6]
    return statistics.median(core) if len(core) >= 3 else med
