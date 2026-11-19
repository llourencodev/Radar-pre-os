"""Servidor web do Radar de Preços (API + interface)."""
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import collector, config, coupons, db, instant
from .stores.catalog import OFF_STORES, STORES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
_stop = threading.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    if config.API_MODE:
        # servidor público de busca instantânea (Render): sem agendador nem coleta automática
        logging.getLogger(__name__).info("Modo api: só /api/buscar e /api/saude")
        yield
        return
    pruned = db.prune_all()  # some da tela o que o filtro atual não aceita
    logging.getLogger(__name__).info("Ofertas desativadas pelo filtro: %s", pruned)
    threading.Thread(target=collector.scheduler_loop, args=(_stop,), daemon=True, name="agendador").start()
    yield
    _stop.set()


app = FastAPI(title="Radar de Preços", version="1.0", lifespan=lifespan)

API_ROUTES = ("/api/buscar", "/api/saude")


@app.middleware("http")
async def api_mode_guard(request: Request, call_next):
    """No modo api (endereço público) só a busca instantânea e a checagem de saúde existem."""
    if config.API_MODE and (request.url.path not in API_ROUTES or request.method not in ("GET", "HEAD", "OPTIONS")):
        return JSONResponse({"detail": "Não encontrado"}, status_code=404)
    return await call_next(request)


@app.middleware("http")
async def no_cache(request: Request, call_next):
    """Os dados mudam a cada coleta: a API nunca vem do cache do navegador, e a interface é sempre conferida."""
    resp = await call_next(request)
    path = request.url.path
    if path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    elif path == "/" or path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


# o site publicado (GitHub Pages) chama a busca instantânea de outro endereço
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["GET"], allow_headers=[],
                   allow_credentials=False, max_age=3600)


def client_ip(request: Request) -> str:
    """IP de quem buscou, para o limite por IP.

    Fora do modo api, só vale o endereço da conexão (nenhum cabeçalho é confiável). No modo api o serviço fica
    atrás do proxy do Render, que acrescenta o IP real de quem conectou ao FINAL do X-Forwarded-For; os itens
    anteriores podem ter sido inventados pelo cliente, então só o último é usado. Outros cabeçalhos de IP
    (True-Client-IP, CF-Connecting-IP) são ignorados porque o cliente também pode enviá-los."""
    if config.API_MODE:
        xff = request.headers.get("x-forwarded-for", "")
        last = xff.split(",")[-1].strip() if xff else ""
        if last:
            return last
    return request.client.host if request.client else "?"


@app.get("/api/saude")
def saude():
    return {"ok": True, "mode": config.MODE}


@app.get("/api/buscar")
def buscar(request: Request, q: str = ""):
    """Busca instantânea: consulta as lojas na hora (até 30 s), sem cadastrar o produto. Cache de 10 min por termo."""
    if not instant.limiter.allow(client_ip(request)):
        raise HTTPException(429, f"Muitas buscas seguidas. Espere um minuto (limite de {config.SEARCH_RATE_PER_MIN} por minuto).")
    try:
        return instant.search(q)
    except instant.SearchError as e:
        raise HTTPException(e.status, e.detail) from e


def _not_found(x):
    if not x:
        raise HTTPException(404, "Produto não encontrado")
    return x


# ---------------------------------------------------------------- busca e produtos monitorados
class SearchIn(BaseModel):
    q: str = Field(min_length=2, max_length=120)
    exclude: str = ""
    target_price: float | None = None


@app.post("/api/search")
def search(s: SearchIn):
    w = db.upsert_watch(s.q, s.exclude, s.target_price)
    collector.collect_async(w["id"])
    return {"id": w["id"]}


@app.get("/api/watches")
def watches():
    out = []
    for w in db.list_watches():
        w["running"] = collector.State.running.get(w["id"])
        out.append(w)
    return out


@app.get("/api/watches/{wid}")
def watch(wid: int, inactive: bool = False):
    w = _not_found(db.get_watch(wid))
    w["items"] = db.annotated_offers(w, include_inactive=inactive)
    w["running"] = collector.State.running.get(wid)
    w["history"] = db.watch_history(wid)
    ref = w.get("ref_price")
    best_stores = {o["store"] for o in w["items"][:15]}
    cps = [c for c in db.list_coupons() if c["store"] in best_stores]
    for c in cps:
        c["saving"] = round(coupons.score(c, (w.get("best") or {}).get("price") or ref), 2)
    w["coupons"] = sorted(cps, key=lambda c: -c["saving"])[:12]
    return w


class WatchPatch(BaseModel):
    exclude: str | None = None
    target_price: float | None = None
    enabled: bool | None = None


@app.patch("/api/watches/{wid}")
def patch_watch(wid: int, p: WatchPatch):
    _not_found(db.get_watch(wid))
    fields = {k: (int(v) if isinstance(v, bool) else v) for k, v in p.model_dump(exclude_unset=True).items()}
    db.update_watch(wid, **fields)
    return db.get_watch(wid)


@app.delete("/api/watches/{wid}")
def remove_watch(wid: int):
    db.delete_watch(wid)
    return {"ok": True}


@app.post("/api/watches/{wid}/refresh")
def refresh_watch(wid: int):
    _not_found(db.get_watch(wid))
    return {"started": collector.collect_async(wid)}


@app.get("/api/offers/{oid}/history")
def offer_history(oid: int):
    return db.history(oid)


# ---------------------------------------------------------------- painel
@app.get("/api/dashboard")
def dashboard():
    ws = db.list_watches()
    hot, new = [], []
    for w in ws:
        for o in db.annotated_offers(w):
            o["query"] = w["query"]
            if {"bugao", "bug", "alvo"} & set(o["flags"]) or ("abaixo" in o["flags"] and "queda" in o["flags"]):
                hot.append(o)
            if "nova" in o["flags"]:
                new.append(o)
    hot.sort(key=lambda o: ("bugao" not in o["flags"], o["ratio"] or 1))
    new.sort(key=lambda o: o["first_seen"], reverse=True)
    cps = db.list_coupons(only_codes=True)
    for c in cps:
        c["saving"] = round(coupons.score(c), 2)
    return {
        "watches": ws,
        "hot": hot[:24],
        "bugaos": sum(1 for o in hot if "bugao" in o["flags"]),
        "new": new[:24],
        "coupons": sorted(cps, key=lambda c: -c["saving"])[:12],
        "coupons_total": len(db.list_coupons()),
        "status": status(),
    }


# ---------------------------------------------------------------- cupons
@app.get("/api/coupons")
def list_coupons(store: str | None = None, only_codes: bool = False):
    cps = db.list_coupons(store, only_codes)
    for c in cps:
        c["saving"] = round(coupons.score(c), 2)
    return {"items": cps, "stores": list(coupons.COUPON_STORES), "runs": db.coupon_runs(),
            "running": collector.State.coupons_running}


@app.post("/api/coupons/refresh")
def refresh_coupons():
    if collector.State.coupons_running:
        return {"started": False}
    threading.Thread(target=collector.collect_coupons, daemon=True).start()
    return {"started": True}


# ---------------------------------------------------------------- situação
@app.get("/api/status")
def status():
    running = {wid: r for wid, r in collector.State.running.items()}
    return {
        "running": bool(running) or collector.State.coupons_running,
        "watches_running": running,
        "coupons_running": collector.State.coupons_running,
        "auto_update": config.AUTO_UPDATE,
        "interval_min": config.INTERVAL_MIN,
        "scheduler_alive": collector.State.scheduler_alive,
        "telegram": bool(config.TELEGRAM_TOKEN and config.TELEGRAM_CHAT_ID),
        # horário da última coleta (produtos ou cupons): a interface recarrega quando ele muda
        "last_update": last_update(),
    }


def last_update() -> str | None:
    r = db.one("SELECT MAX(at) AS at FROM (SELECT MAX(last_run) AS at FROM watches UNION ALL SELECT MAX(at) FROM coupon_runs)")
    return r["at"] if r else None


@app.get("/api/stores")
def stores():
    active = {s[0] for s in collector.enabled_stores()}
    runs = db.rows("SELECT r.*, w.query FROM store_runs r JOIN watches w ON w.id=r.watch_id ORDER BY r.at DESC")
    out = []
    for sid, name, _fn, kind, note in STORES:
        mine = [r for r in runs if r["store"] == name]
        out.append({"id": sid, "name": name, "kind": kind, "note": note, "enabled": sid in active, "last": mine[0] if mine else None,
                    "ok": sum(1 for r in mine if r["status"] == "ok"), "runs": len(mine)})
    for sid, name, why in OFF_STORES:
        out.append({"id": sid, "name": name, "kind": "loja", "note": why, "enabled": False, "last": None, "ok": 0, "runs": 0})
    return out


# ---------------------------------------------------------------- interface
app.mount("/static", StaticFiles(directory=config.WEB_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(config.WEB_DIR / "index.html")
