"""Banco SQLite: produtos monitorados, ofertas, histórico de preços e cupons."""
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

from . import config
from .matching import reference_price, relevance, strict_match

_lock = threading.RLock()
REF_EXCLUDED_STORES = ("Zoom", "AliExpress")
_conn: sqlite3.Connection | None = None


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
    return _conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS watches (
  id INTEGER PRIMARY KEY, query TEXT NOT NULL UNIQUE, exclude TEXT DEFAULT '', target_price REAL,
  enabled INTEGER DEFAULT 1, created_at TEXT, last_run TEXT, runs INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS offers (
  id INTEGER PRIMARY KEY, watch_id INTEGER NOT NULL, store TEXT, title TEXT, url TEXT, price REAL, old_price REAL,
  image TEXT, seller TEXT, installments TEXT, condition TEXT, kind TEXT, via TEXT, coupon TEXT, posted_at TEXT, note TEXT,
  first_seen TEXT, last_seen TEXT, min_price REAL, prev_price REAL, price_changed_at TEXT, active INTEGER DEFAULT 1,
  first_run INTEGER DEFAULT 0, UNIQUE(watch_id, url)
);
CREATE INDEX IF NOT EXISTS ix_offers_watch ON offers(watch_id, active, price);
CREATE TABLE IF NOT EXISTS history (offer_id INTEGER, price REAL, seen_at TEXT);
CREATE INDEX IF NOT EXISTS ix_hist ON history(offer_id, seen_at);
CREATE TABLE IF NOT EXISTS store_runs (
  watch_id INTEGER, store TEXT, status TEXT, error TEXT, seen INTEGER, matched INTEGER, at TEXT, PRIMARY KEY(watch_id, store)
);
CREATE TABLE IF NOT EXISTS coupons (
  id INTEGER PRIMARY KEY, store TEXT, code TEXT, title TEXT, url TEXT, source TEXT, expires TEXT, min_value REAL,
  pct REAL, amount REAL, first_seen TEXT, last_seen TEXT, active INTEGER DEFAULT 1, UNIQUE(store, code, title)
);
CREATE TABLE IF NOT EXISTS coupon_runs (store TEXT PRIMARY KEY, status TEXT, error TEXT, found INTEGER, at TEXT);
"""


def init_db() -> None:
    with _lock:
        conn().executescript(SCHEMA)
        conn().commit()


def rows(sql: str, args=()) -> list[dict]:
    with _lock:
        return [dict(r) for r in conn().execute(sql, args).fetchall()]


def one(sql: str, args=()) -> dict | None:
    r = rows(sql, args)
    return r[0] if r else None


def run(sql: str, args=()) -> int:
    with _lock:
        cur = conn().execute(sql, args)
        conn().commit()
        return cur.lastrowid


# ------------------------------------------------------------------ produtos monitorados
def upsert_watch(query: str, exclude: str = "", target_price: float | None = None) -> dict:
    q = " ".join(query.split())
    w = one("SELECT * FROM watches WHERE lower(query)=lower(?)", (q,))
    if w:
        if exclude or target_price is not None:
            update_watch(w["id"], exclude=exclude or w["exclude"], target_price=target_price if target_price is not None else w["target_price"])
        return get_watch(w["id"])
    wid = run("INSERT INTO watches(query, exclude, target_price, created_at) VALUES (?,?,?,?)", (q, exclude, target_price, now()))
    return get_watch(wid)


def update_watch(wid: int, **fields) -> None:
    allowed = {k: v for k, v in fields.items() if k in ("exclude", "target_price", "enabled", "last_run", "runs")}
    if allowed:
        run(f"UPDATE watches SET {', '.join(k + '=?' for k in allowed)} WHERE id=?", (*allowed.values(), wid))


def delete_watch(wid: int) -> None:
    with _lock:
        c = conn()
        c.execute("DELETE FROM history WHERE offer_id IN (SELECT id FROM offers WHERE watch_id=?)", (wid,))
        c.execute("DELETE FROM offers WHERE watch_id=?", (wid,))
        c.execute("DELETE FROM store_runs WHERE watch_id=?", (wid,))
        c.execute("DELETE FROM watches WHERE id=?", (wid,))
        c.commit()


def get_watch(wid: int) -> dict | None:
    w = one("SELECT * FROM watches WHERE id=?", (wid,))
    if w:
        w.update(_watch_stats(w))
    return w


def list_watches() -> list[dict]:
    ws = rows("SELECT * FROM watches ORDER BY created_at DESC")
    for w in ws:
        w.update(_watch_stats(w))
    return ws


def _watch_stats(w: dict) -> dict:
    offers = annotated_offers(w)
    prods = [o for o in offers if o["kind"] == "produto"]
    best = min(prods, key=lambda o: o["price"]) if prods else None
    return {
        "offers": len(offers),
        "best": best,
        "ref_price": offers[0]["ref_price"] if offers else None,
        "new": sum(1 for o in offers if "nova" in o["flags"]),
        "bugs": sum(1 for o in offers if {"bug", "bugao"} & set(o["flags"])),
        "bugaos": sum(1 for o in offers if "bugao" in o["flags"]),
        "stores": rows("SELECT store, status, error, seen, matched, at FROM store_runs WHERE watch_id=? ORDER BY store", (w["id"],)),
    }


# ------------------------------------------------------------------ ofertas
def save_results(wid: int, results: list, first_run: bool) -> list[dict]:
    """Grava as ofertas de uma coleta. Devolve as ofertas que surgiram agora (para alertas)."""
    ts = now()
    fresh = []
    with _lock:
        c = conn()
        for res in results:
            c.execute("INSERT OR REPLACE INTO store_runs VALUES (?,?,?,?,?,?,?)",
                      (wid, res.store, res.status, res.error, res.seen, len(res.offers), ts))
            if res.status not in ("ok", "vazio"):
                continue
            urls = []
            for o in res.offers:
                urls.append(o.url)
                old = c.execute("SELECT id, price, min_price FROM offers WHERE watch_id=? AND url=?", (wid, o.url)).fetchone()
                if old is None:
                    cur = c.execute(
                        "INSERT INTO offers(watch_id, store, title, url, price, old_price, image, seller, installments, condition, kind,"
                        " via, coupon, posted_at, note, first_seen, last_seen, min_price, active, first_run) VALUES"
                        " (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)",
                        (wid, o.store, o.title, o.url, o.price, o.old_price, o.image, o.seller, o.installments, o.condition,
                         o.kind, o.via, o.coupon, o.posted_at, o.note, ts, ts, o.price, int(first_run)))
                    c.execute("INSERT INTO history VALUES (?,?,?)", (cur.lastrowid, o.price, ts))
                    if not first_run:
                        fresh.append({"id": cur.lastrowid, **o.as_dict()})
                else:
                    changed = abs((old["price"] or 0) - o.price) > 0.009
                    c.execute(
                        "UPDATE offers SET title=?, price=?, old_price=?, image=COALESCE(?, image), seller=?, installments=?, via=COALESCE(?, via),"
                        " coupon=COALESCE(?, coupon), note=?, last_seen=?, active=1, min_price=MIN(COALESCE(min_price, ?), ?)"
                        + (", prev_price=?, price_changed_at=?" if changed else "") + " WHERE id=?",
                        (o.title, o.price, o.old_price, o.image, o.seller, o.installments, o.via, o.coupon, o.note, ts, o.price, o.price,
                         *((old["price"], ts) if changed else ()), old["id"]))
                    if changed:
                        c.execute("INSERT INTO history VALUES (?,?,?)", (old["id"], o.price, ts))
                        if o.price < old["price"] * 0.95:
                            fresh.append({"id": old["id"], "drop_from": old["price"], **o.as_dict()})
            # ofertas que sumiram da loja nesta coleta ficam inativas
            if res.status == "ok":
                marks = ",".join("?" * len(urls)) or "''"
                c.execute(f"UPDATE offers SET active=0 WHERE watch_id=? AND store=? AND url NOT IN ({marks})", (wid, res.store, *urls))
        c.execute("UPDATE watches SET last_run=?, runs=runs+1 WHERE id=?", (ts, wid))
        c.commit()
    prune_offers(wid)
    return [f for f in fresh if one("SELECT active FROM offers WHERE id=?", (f["id"],))["active"]]


def _ref_base(offers: list[dict]) -> list[float]:
    # referência só com lojas brasileiras: sem importados (AliExpress), comparadores (Zoom),
    # promoções de comunidade nem usados
    return [o["price"] for o in offers if o["kind"] == "produto" and o["condition"] != "usado"
            and not (o["store"] or "").startswith(REF_EXCLUDED_STORES)]


def prune_offers(wid: int) -> int:
    """Reavalia as ofertas ativas com o filtro atual e desativa as que não passam. Devolve quantas saíram.

    1) o título precisa passar no filtro de relevância (termos inteiros, sem cara de acessório);
    2) coerência de preço: abaixo de 20% da referência só fica se o título casar muito bem
       (e nunca abaixo de 5%, que é preço simbólico: R$ 0,01, "R$ 300 de desconto"...).
    """
    w = one("SELECT * FROM watches WHERE id=?", (wid,))
    if not w:
        return 0
    exclude = [x.strip() for x in (w.get("exclude") or "").split(",") if x.strip()]
    offers = rows("SELECT id, store, title, price, kind, condition FROM offers WHERE watch_id=? AND active=1", (wid,))
    drop = {o["id"] for o in offers if not relevance(w["query"], o["title"] or "", exclude)[0]}
    kept = [o for o in offers if o["id"] not in drop]
    drop |= {o["id"] for o in kept if o["price"] < 5}  # preço simbólico (R$ 0,01 de "cupom", "R$ 300 de desconto")
    kept = [o for o in kept if o["id"] not in drop]
    ref = reference_price(_ref_base(kept))
    if ref:
        for o in kept:
            if o["price"] < ref * config.FLOOR_RATIO and (o["price"] < ref * 0.05 or not strict_match(w["query"], o["title"] or "")):
                drop.add(o["id"])
    if drop:
        with _lock:
            conn().execute(f"UPDATE offers SET active=0 WHERE id IN ({','.join('?' * len(drop))})", tuple(drop))
            conn().commit()
    return len(drop)


def prune_all() -> dict[int, int]:
    return {w["id"]: prune_offers(w["id"]) for w in rows("SELECT id FROM watches")}


def annotated_offers(w: dict, include_inactive: bool = False) -> list[dict]:
    """Ofertas com as marcações: bug de preço, abaixo da média, nova, queda, menor histórico."""
    offers = rows("SELECT * FROM offers WHERE watch_id=?" + ("" if include_inactive else " AND active=1") + " ORDER BY price",
                  (w["id"],))
    ref = reference_price(_ref_base(offers))
    new_since = (datetime.now(timezone.utc) - timedelta(hours=config.NEW_HOURS)).isoformat()
    for o in offers:
        f = []
        r = o["price"] / ref if ref else None
        o["ref_price"] = ref
        o["ratio"] = round(r, 3) if r else None
        if o["kind"] == "promo":
            # postagem de comunidade: só conta como bug se for recente e não estiver encerrada
            recent = bool(o["posted_at"]) and o["posted_at"] >= (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()[:10]
            if o["note"] and "encerrada" in o["note"]:
                f.append("encerrada")
                r = None
                o["ratio"] = None
            elif not recent:
                f.append("antiga" if o["posted_at"] else "sem_data")
                r = None
            if r is None:
                o["ratio"] = None
        if r is not None:
            if r <= config.BUGAO_RATIO:
                f.append("bugao")
                if r < config.SUSPECT_RATIO:
                    f.append("suspeito")  # desconto extremo: confira o vendedor
            elif r <= config.BUG_RATIO:
                f.append("bug")
            elif r <= config.DEAL_RATIO:
                f.append("abaixo")
        if o["first_seen"] >= new_since and not o["first_run"]:
            f.append("nova")
        if o["prev_price"] and o["price"] < o["prev_price"] * 0.98:
            f.append("queda")
        if o["old_price"] and o["old_price"] > o["price"] * 1.4:
            f.append("desconto_alto")
        if w.get("target_price") and o["price"] <= w["target_price"]:
            f.append("alvo")
        if o["condition"] == "usado":
            f.append("usado")
        o["flags"] = f
    return offers


def history(offer_id: int) -> list[dict]:
    return rows("SELECT price, seen_at FROM history WHERE offer_id=? ORDER BY seen_at", (offer_id,))


def watch_history(wid: int) -> list[dict]:
    """Menor preço por dia do produto (todas as lojas)."""
    return rows("SELECT substr(h.seen_at,1,10) AS day, MIN(h.price) AS price FROM history h JOIN offers o ON o.id=h.offer_id"
                " WHERE o.watch_id=? AND o.kind='produto' AND COALESCE(o.condition,'')<>'usado' GROUP BY day ORDER BY day", (wid,))


# ------------------------------------------------------------------ cupons
def save_coupons(store: str, coupons: list, errors: list[str]) -> int:
    ts = now()
    new = 0
    with _lock:
        c = conn()
        if coupons:
            c.execute("UPDATE coupons SET active=0 WHERE store=?", (store,))
        for cp in coupons:
            d = cp.as_dict()
            cur = c.execute("UPDATE coupons SET last_seen=?, active=1, url=?, source=?, expires=?, min_value=?, pct=?, amount=?"
                            " WHERE store=? AND COALESCE(code,'')=COALESCE(?, '') AND title=?",
                            (ts, d["url"], d["source"], d["expires"], d["min_value"], d["pct"], d["amount"], store, d["code"], d["title"]))
            if cur.rowcount == 0:
                c.execute("INSERT OR IGNORE INTO coupons(store, code, title, url, source, expires, min_value, pct, amount, first_seen, last_seen)"
                          " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                          (store, d["code"], d["title"], d["url"], d["source"], d["expires"], d["min_value"], d["pct"], d["amount"], ts, ts))
                new += 1
        c.execute("INSERT OR REPLACE INTO coupon_runs VALUES (?,?,?,?,?)",
                  (store, "ok" if coupons else ("erro" if errors else "vazio"), "; ".join(errors) or None, len(coupons), ts))
        c.commit()
    return new


def list_coupons(store: str | None = None, only_codes: bool = False) -> list[dict]:
    sql = "SELECT * FROM coupons WHERE active=1"
    args: list = []
    if store:
        sql += " AND store=?"
        args.append(store)
    if only_codes:
        sql += " AND code IS NOT NULL"
    return rows(sql + " ORDER BY COALESCE(pct,0) DESC, COALESCE(amount,0) DESC, last_seen DESC", args)


def coupon_runs() -> list[dict]:
    return rows("SELECT * FROM coupon_runs ORDER BY store")
