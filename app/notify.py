"""Avisos opcionais no Telegram (configure TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID no .env)."""
import logging

from . import config, http

log = logging.getLogger(__name__)
LABELS = {"bug": "Possível bug de preço", "alvo": "Abaixo do seu preço alvo", "queda": "Preço caiu"}


def brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def send(watch: dict, offer: dict) -> None:
    if not (config.TELEGRAM_TOKEN and config.TELEGRAM_CHAT_ID):
        return
    if "bugao" in offer["flags"] and offer.get("ratio"):
        tag = f"BUGÃO -{round((1 - offer['ratio']) * 100)}%"
        if "suspeito" in offer["flags"]:
            tag += " (suspeito: confira o vendedor)"
    else:
        tag = next((LABELS[f] for f in ("bug", "alvo", "queda") if f in offer["flags"]), "Nova oferta")
    ref = f" (referência {brl(offer['ref_price'])})" if offer.get("ref_price") else ""
    text = (f"🎯 {tag}: {watch['query']}\n{offer['title']}\n{offer['store']}: {brl(offer['price'])}{ref}\n{offer['url']}")
    try:
        http.post(f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage",
                  json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": False})
    except Exception as e:  # noqa: BLE001
        log.warning("Telegram falhou: %s", e)
