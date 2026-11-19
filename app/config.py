"""Configuração central: lê variáveis de ambiente e o arquivo .env (sem dependências extras)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
WEB_DIR = BASE_DIR / "web"


def _load_dotenv() -> None:
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "sim", "yes", "on")


HOST = os.environ.get("PRECOS_HOST", "127.0.0.1")
PORT = _int("PRECOS_PORT", 8010)
DB_PATH = Path(os.environ.get("PRECOS_DB", str(DATA_DIR / "precos.db")))

# Monitoramento automático dos produtos salvos
INTERVAL_MIN = _int("PRECOS_INTERVAL_MIN", 30)
AUTO_UPDATE = _bool("PRECOS_AUTO_UPDATE", True)
COLLECT_ON_START = _bool("PRECOS_COLLECT_ON_START", True)
COUPON_INTERVAL_MIN = _int("PRECOS_COUPON_INTERVAL_MIN", 120)
WORKERS = _int("PRECOS_WORKERS", 8)

# Detecção de bug de preço (fração do preço de referência = mediana das ofertas)
BUGAO_RATIO = _float("PRECOS_BUGAO_RATIO", 0.50)    # 50% ou mais de desconto sobre a referência = BUGÃO
BUG_RATIO = _float("PRECOS_BUG_RATIO", 0.70)        # abaixo de 70% da mediana = possível erro de preço
DEAL_RATIO = _float("PRECOS_DEAL_RATIO", 0.88)      # abaixo de 88% da mediana = abaixo da média
SUSPECT_RATIO = _float("PRECOS_SUSPECT_RATIO", 0.25)  # abaixo de 25% = também marcado suspeito (confira o vendedor)
FLOOR_RATIO = _float("PRECOS_FLOOR_RATIO", 0.20)  # abaixo de 20% da referência só fica se o título casar muito bem
NEW_HOURS = _int("PRECOS_NEW_HOURS", 24)

# Modo de execução: "local" (padrão: monitoramento automático) ou "api" (servidor público de busca instantânea,
# por exemplo no Render: sem agendador nem coleta automática, só /api/buscar e /api/saude)
MODE = os.environ.get("PRECOS_MODE", "local").strip().lower()
API_MODE = MODE == "api"
# Busca instantânea (/api/buscar)
SEARCH_TIMEOUT = _int("PRECOS_SEARCH_TIMEOUT", 30)        # segundos; lojas mais lentas ficam de fora
SEARCH_CACHE_MIN = _int("PRECOS_SEARCH_CACHE_MIN", 10)    # cache por termo
SEARCH_RATE_PER_MIN = _int("PRECOS_SEARCH_RATE", 10)      # buscas por minuto por IP
SEARCH_PARALLEL = _int("PRECOS_SEARCH_PARALLEL", 2)       # buscas rodando ao mesmo tempo
SEARCH_RATE_GLOBAL = _int("PRECOS_SEARCH_RATE_GLOBAL", 60) # buscas novas por minuto no servidor todo (cache não conta)
CORS_ORIGINS = [o.strip() for o in os.environ.get(
    "PRECOS_CORS_ORIGINS", "https://llourencodev.github.io,http://localhost:8010").split(",") if o.strip()]

HTTP_TIMEOUT = _int("PRECOS_HTTP_TIMEOUT", 25)
HOST_MIN_INTERVAL = _float("PRECOS_HOST_MIN_INTERVAL", 1.5)
USER_AGENT = os.environ.get(
    "PRECOS_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
)

# Mercado Livre: token da API oficial (opcional). Sem ele a busca usa o site, que costuma pedir verificação.
ML_ACCESS_TOKEN = os.environ.get("ML_ACCESS_TOKEN", "").strip()

# Aviso opcional no Telegram quando surgir bug de preço ou oferta abaixo do preço alvo
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

DATA_DIR.mkdir(parents=True, exist_ok=True)
