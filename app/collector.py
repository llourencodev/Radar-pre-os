"""Executa as buscas nas lojas, filtra os anúncios relevantes, grava e dispara alertas."""
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from . import config, coupons, db, http, notify
from .matching import relevance
from .stores.base import StoreResult
from .stores.catalog import STORES

log = logging.getLogger(__name__)


class State:
    running: dict[int, dict] = {}        # watch_id -> {"done": n, "total": n, "stores": {...}}
    coupons_running = False
    coupons_last: str | None = None
    scheduler_alive = False
    lock = threading.Lock()


def enabled_stores() -> list:
    disabled = {s.strip() for s in (os.environ.get("PRECOS_DISABLED_STORES", "")).split(",") if s.strip()}
    return [s for s in STORES if s[0] not in disabled]


def _one_store(sid: str, name: str, fn, query: str, exclude: list[str]) -> StoreResult:
    res = StoreResult(store=name)
    t0 = time.monotonic()
    try:
        offers = fn(query)
        res.seen = len(offers)
        keep, seen = [], set()
        for o in offers:
            ok, _why = relevance(query, o.title, exclude)
            if ok and o.url not in seen and o.price > 0:
                seen.add(o.url)
                keep.append(o)
        res.offers = keep
        res.status = "ok" if keep else "vazio"
        if not offers:
            res.error = "Nenhum anúncio ativo lido (sem resultados no momento, ou a página mudou)"
    except http.Blocked as e:
        res.status, res.error = "bloqueado", str(e)
    except Exception as e:  # noqa: BLE001
        res.status, res.error = "erro", f"{type(e).__name__}: {e}"[:300]
        log.warning("%s falhou para '%s': %s", name, query, e)
    log.info("%-18s %-8s lidos=%3d relevantes=%3d  %.1fs", name, res.status, res.seen, len(res.offers), time.monotonic() - t0)
    return res


def collect(wid: int) -> dict | None:
    w = db.get_watch(wid)
    if not w:
        return None
    with State.lock:
        if wid in State.running:
            return None
        stores = enabled_stores()
        State.running[wid] = {"done": 0, "total": len(stores), "stores": {}}
    try:
        exclude = [x.strip() for x in (w.get("exclude") or "").split(",") if x.strip()]
        results = []
        with ThreadPoolExecutor(max_workers=config.WORKERS) as ex:
            futs = {ex.submit(_one_store, sid, name, fn, w["query"], exclude): name for sid, name, fn, _t, _n in stores}
            for f in futs:
                r = f.result()
                results.append(r)
                with State.lock:
                    State.running[wid]["done"] += 1
                    State.running[wid]["stores"][r.store] = r.status
        fresh = db.save_results(wid, results, first_run=(w["runs"] or 0) == 0)
        _alert(db.get_watch(wid), fresh)
        return {"new": len(fresh)}
    finally:
        with State.lock:
            State.running.pop(wid, None)


def collect_async(wid: int) -> bool:
    if wid in State.running:
        return False
    threading.Thread(target=collect, args=(wid,), daemon=True, name=f"busca-{wid}").start()
    return True


def _alert(w: dict, fresh: list[dict]) -> None:
    if not w or not fresh:
        return
    flagged = {o["id"]: o for o in db.annotated_offers(w)}
    for f in fresh:
        o = flagged.get(f["id"])
        if not o:
            continue
        if {"bugao", "bug", "alvo"} & set(o["flags"]) or ("queda" in o["flags"] and "abaixo" in o["flags"]):
            notify.send(w, o)


def collect_coupons() -> None:
    if State.coupons_running:
        return
    State.coupons_running = True
    try:
        for store in coupons.COUPON_STORES:
            found, errors = coupons.fetch_store(store)
            # agrupa duplicatas vindas de agregadores diferentes
            uniq = {}
            for c in found:
                uniq.setdefault((c.code or c.title).lower(), c)
            db.save_coupons(store, list(uniq.values()), errors)
        State.coupons_last = db.now()
    finally:
        State.coupons_running = False


def scheduler_loop(stop: threading.Event) -> None:
    State.scheduler_alive = True
    first = True
    last_coupons = 0.0
    try:
        while not stop.is_set():
            if config.AUTO_UPDATE or (first and config.COLLECT_ON_START):
                limit = (datetime.now(timezone.utc) - timedelta(minutes=config.INTERVAL_MIN)).isoformat()
                for w in db.rows("SELECT id, last_run FROM watches WHERE enabled=1"):
                    if not w["last_run"] or w["last_run"] < limit or (first and config.COLLECT_ON_START):
                        collect(w["id"])
                if time.time() - last_coupons > config.COUPON_INTERVAL_MIN * 60 or (first and config.COLLECT_ON_START):
                    collect_coupons()
                    last_coupons = time.time()
            first = False
            stop.wait(60)
    finally:
        State.scheduler_alive = False
