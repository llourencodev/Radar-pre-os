"""Busca instantânea: consulta as lojas na hora para qualquer termo, sem cadastrar o produto.

Usada pelo site publicado (GitHub Pages) através da API no Render (PRECOS_MODE=api) e também pelo servidor local.
O endereço é público, então há proteção básica contra abuso: termo de 2 a 80 caracteres, limite de buscas por IP,
cache de 10 minutos por termo e no máximo SEARCH_PARALLEL buscas rodando ao mesmo tempo.
"""
import logging
import threading
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone

from . import collector, config, coupons, db
from .matching import norm

log = logging.getLogger(__name__)


class SearchError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


# ------------------------------------------------------------------ proteção contra abuso
class RateLimiter:
    """Janela deslizante: no máximo `limit` chamadas por `window` segundos para cada chave (IP)."""

    def __init__(self, limit: int, window: float = 60.0):
        self.limit, self.window = limit, window
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            if len(self.hits) > 5000:  # não deixa a memória crescer com IPs antigos
                for k in [k for k, v in self.hits.items() if not v or now - v[-1] > self.window]:
                    del self.hits[k]
            return True


limiter = RateLimiter(config.SEARCH_RATE_PER_MIN)
_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()
_CACHE_MAX = 500
# travas por termo em número fixo (o mesmo termo cai sempre na mesma trava; a memória não cresce)
_key_locks = [threading.Lock() for _ in range(64)]
# vagas de busca: uma vaga só é devolvida quando TODAS as lojas daquela busca terminaram (mesmo as que
# passaram do tempo e ficaram de fora da resposta), então lojas lentas não acumulam threads sem limite
_slots = threading.BoundedSemaphore(config.SEARCH_PARALLEL)
# um único conjunto de threads para todas as buscas instantâneas
_pool = ThreadPoolExecutor(max_workers=max(4, config.SEARCH_PARALLEL * 16), thread_name_prefix="busca")
_coupons_started = 0.0


def clean_query(q: str | None) -> str:
    q = " ".join((q or "").split())
    if not 2 <= len(q) <= 80 or len(norm(q).replace(" ", "")) < 2:
        raise SearchError(422, "Digite de 2 a 80 caracteres.")
    return q


def cache_key(q: str) -> str:
    return norm(q)


# ------------------------------------------------------------------ busca
def search(q: str) -> dict:
    q = clean_query(q)
    key = cache_key(q)
    hit = _cached(key)
    if hit:
        return hit
    with _key_locks[hash(key) % len(_key_locks)]:   # duas pessoas buscando o mesmo termo: uma consulta só
        hit = _cached(key)
        if hit:
            return hit
        if not _slots.acquire(timeout=config.SEARCH_TIMEOUT):
            raise SearchError(503, "O servidor está ocupado com outras buscas. Tente de novo em instantes.")
        res = _run(q)   # _run devolve a vaga quando a última loja terminar
        with _cache_lock:
            now = time.monotonic()
            _cache[key] = (now, res)
            for k in [k for k, (t, _) in _cache.items() if now - t > config.SEARCH_CACHE_MIN * 60]:
                del _cache[k]
            while len(_cache) > _CACHE_MAX:
                del _cache[min(_cache, key=lambda k: _cache[k][0])]
        return {**res, "cached": False}


def _cached(key: str) -> dict | None:
    with _cache_lock:
        c = _cache.get(key)
    if c and time.monotonic() - c[0] < config.SEARCH_CACHE_MIN * 60:
        return {**c[1], "cached": True}
    return None


def _run(q: str) -> dict:
    """Roda a busca em todas as lojas. Precisa ser chamada com uma vaga de _slots: devolve a vaga sozinha."""
    try:
        stores = collector.enabled_stores()
    except Exception:
        _slots.release()
        raise
    t0 = time.monotonic()
    if not stores:
        _slots.release()
        futs = {}
    else:
        left = [len(stores), False]          # [lojas ainda rodando, vaga já devolvida]
        left_lock = threading.Lock()

        def give_back(reason: str | None = None):
            with left_lock:
                if left[1]:
                    return
                left[1] = True
            if reason:
                log.warning("Busca '%s': vaga devolvida por %s (%s loja(s) ainda rodando)", q, reason, left[0])
            _slots.release()

        def finished(_f):
            with left_lock:
                left[0] -= 1
                last = left[0] == 0
            if last:
                give_back()

        # trava de segurança: mesmo que uma loja trave, a vaga volta depois de 3x o tempo da busca
        # (as threads do conjunto compartilhado são limitadas, então uma loja presa não multiplica threads)
        guard = threading.Timer(config.SEARCH_TIMEOUT * 3, give_back, args=("tempo limite",))
        guard.daemon = True
        guard.start()

        futs = {}
        for sid, name, fn, _k, _n in stores:
            f = _pool.submit(collector._one_store, sid, name, fn, q, [])
            futs[f] = name
            f.add_done_callback(finished)
    done, _pending = wait(futs, timeout=config.SEARCH_TIMEOUT)   # lojas lentas ficam de fora da resposta

    now = db.now()
    offers, status = [], []
    for f, name in futs.items():
        if f in done and not f.exception():
            r = f.result()
            status.append({"store": r.store, "status": r.status, "error": r.error, "seen": r.seen, "matched": len(r.offers), "at": now})
            for o in r.offers:
                d = o.as_dict()
                d.update(first_seen=now, last_seen=now, first_run=1, prev_price=None, min_price=d["price"])
                offers.append(d)
        else:
            status.append({"store": name, "status": "tempo esgotado", "seen": 0, "matched": 0, "at": now,
                           "error": f"A loja não respondeu em {config.SEARCH_TIMEOUT} s"})

    # mesma coerência de preço e as mesmas marcações das páginas de produto
    drop = db.incoherent(q, offers)
    offers = [o for i, o in enumerate(offers) if i not in drop]
    seen, uniq = set(), []
    for o in sorted(offers, key=lambda o: o["price"]):
        if o["url"] not in seen:
            seen.add(o["url"])
            uniq.append(o)
    for i, o in enumerate(uniq, 1):
        o["id"] = -i            # negativo: oferta da busca instantânea (não tem histórico guardado)
        o["query"] = q
    items = db.annotate(uniq)
    for st in status:
        st["matched"] = sum(1 for o in items if o["store"] == st["store"])

    prods = [o for o in items if o["kind"] == "produto" and o.get("condition") != "usado"]
    best = min(prods, key=lambda o: o["price"]) if prods else None
    present = {o["store"] for o in items} | {o["via"] for o in items if o.get("via")}
    _refresh_coupons_if_stale()
    cps = [c for c in db.list_coupons() if c["store"] in present]
    for c in cps:
        c["saving"] = round(coupons.score(c, (best or {}).get("price") or (items[0]["ref_price"] if items else None)), 2)
    return {
        "query": q,
        "generated_at": now,
        "seconds": round(time.monotonic() - t0, 1),
        "ref_price": items[0]["ref_price"] if items else None,
        "best": best,
        "offers": len(items),
        "bugs": sum(1 for o in items if {"bug", "bugao"} & set(o["flags"])),
        "bugaos": sum(1 for o in items if "bugao" in o["flags"]),
        "items": items,
        "stores": sorted(status, key=lambda s: s["store"]),
        "coupons": sorted(cps, key=lambda c: -c["saving"])[:12],
    }


def _refresh_coupons_if_stale() -> None:
    """Os cupons vêm do banco; na API (banco vazio no começo) são atualizados em segundo plano, no máximo a cada 2 h."""
    global _coupons_started
    last = db.one("SELECT MAX(at) AS at FROM coupon_runs")
    limit = (datetime.now(timezone.utc) - timedelta(minutes=config.COUPON_INTERVAL_MIN)).isoformat()
    stale = not last or not last["at"] or last["at"] < limit
    if stale and not collector.State.coupons_running and time.monotonic() - _coupons_started > config.COUPON_INTERVAL_MIN * 60:
        _coupons_started = time.monotonic()
        threading.Thread(target=collector.collect_coupons, daemon=True, name="cupons").start()
