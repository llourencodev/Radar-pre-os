"""Coleta os produtos de config/produtos.json e gera o site estático em site/ (usado pelo GitHub Actions).

Uso:
  python gerar_site.py              coleta e gera o site
  python gerar_site.py --sem-coleta só gera o site com o que já está no banco
  python gerar_site.py --saida pasta
"""
import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

from app import collector, config, db, static_site

PRODUTOS = config.BASE_DIR / "config" / "produtos.json"
# intervalo do agendamento no GitHub (o workflow roda de hora em hora); só aparece no site
SITE_INTERVAL_MIN = int(os.environ.get("PRECOS_SITE_INTERVAL_MIN", "60"))


def sincronizar_produtos() -> list[int]:
    """config/produtos.json é a lista de produtos do site: cria os que faltam, atualiza filtros e preço alvo
    e pausa os que saíram do arquivo (o histórico continua no banco). Devolve os ids publicados."""
    itens = json.loads(PRODUTOS.read_text(encoding="utf-8"))
    ids = []
    for it in itens:
        q = " ".join(str(it.get("query", "")).split())
        if len(q) < 2:
            continue
        w = db.upsert_watch(q)
        db.update_watch(w["id"], exclude=it.get("exclude") or "", target_price=it.get("target_price"),
                        enabled=0 if it.get("enabled") is False else 1)
        ids.append(w["id"])
    for w in db.rows("SELECT id FROM watches"):
        if w["id"] not in ids:
            db.update_watch(w["id"], enabled=0)
    return ids


def cupons_vencidos() -> bool:
    last = db.one("SELECT MAX(at) AS at FROM coupon_runs")
    if not last or not last["at"]:
        return True
    limite = (datetime.now(timezone.utc) - timedelta(minutes=config.COUPON_INTERVAL_MIN - 10)).isoformat()
    return last["at"] < limite


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sem-coleta", action="store_true")
    ap.add_argument("--saida", default="site")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("precos.site")

    db.init_db()
    ids = sincronizar_produtos()
    try:
        if not args.sem_coleta:
            for wid in ids:
                w = db.get_watch(wid)
                if w and w["enabled"]:
                    t0 = time.monotonic()
                    collector.collect(wid)
                    log.info("%s coletado em %.0fs", w["query"], time.monotonic() - t0)
            if cupons_vencidos():
                try:  # uma falha nos cupons não impede a publicação
                    collector.collect_coupons()
                except Exception:
                    log.exception("Falha na coleta de cupons (o site é publicado mesmo assim)")
        db.prune_all()
        info = static_site.export(config.BASE_DIR / args.saida, ids, SITE_INTERVAL_MIN)
        log.info("Site gerado em %s: %s produtos, %s ofertas, %s cupons",
                 args.saida, info["watches"], info["offers"], info["coupons"])
    finally:
        con = sqlite3.connect(config.DB_PATH)  # grava tudo no arquivo principal antes de guardar o banco
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.close()

    if info["offers"] == 0:
        log.error("Nenhuma oferta no site gerado: a publicação foi cancelada e o site atual continua no ar.")
        sys.exit(1)


if __name__ == "__main__":
    main()
