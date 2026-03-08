"""
whatsapp_agent.py — Bot de WhatsApp con polling via Twilio
Diseñado para ejecutarse cada minuto desde GitHub Actions.
"""

import os
import re
import logging
from datetime import datetime, timezone, timedelta
from twilio.rest import Client
from bot import procesar_mensaje

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

TWILIO_ACCOUNT_SID  = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN   = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_WHATSAPP_NUM = os.environ["TWILIO_WHATSAPP_NUM"]  # ej: whatsapp:+14155238886

# Cuántos minutos hacia atrás miramos mensajes (debe ser >= intervalo del cron)
WINDOW_MINUTES = int(os.environ.get("WINDOW_MINUTES", "2"))


def get_mensajes_nuevos(client: Client) -> list[dict]:
    """Obtiene mensajes recibidos en los últimos WINDOW_MINUTES minutos."""
    desde = datetime.now(timezone.utc) - timedelta(minutes=WINDOW_MINUTES)

    mensajes = client.messages.list(
        to=TWILIO_WHATSAPP_NUM,
        date_sent_after=desde,
    )

    # Filtrar solo mensajes entrantes (de clientes al bot)
    entrantes = [m for m in mensajes if m.direction == "inbound"]
    logger.info(f"📩 {len(entrantes)} mensaje(s) nuevos encontrados.")
    return entrantes


def enviar_respuesta(client: Client, phone: str, texto: str):
    """Envía un mensaje de WhatsApp via Twilio."""
    try:
        client.messages.create(
            from_=TWILIO_WHATSAPP_NUM,
            to=phone,
            body=texto,
        )
        logger.info(f"✅ Respuesta enviada a {phone}")
    except Exception as e:
        logger.error(f"❌ Error enviando mensaje a {phone}: {e}")


def main():
    logger.info("🔍 Revisando mensajes de WhatsApp...")

    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    mensajes = get_mensajes_nuevos(client)

    if not mensajes:
        logger.info("✔ Sin mensajes nuevos.")
        return

    procesados = 0
    for msg in mensajes:
        phone  = msg.from_   # ej: whatsapp:+34612345678
        texto  = msg.body
        msg_id = msg.sid

        logger.info(f"📱 Procesando mensaje de {phone}: {texto[:80]}")

        try:
            respuesta = procesar_mensaje(phone=phone, texto=texto, msg_id=msg_id)
            enviar_respuesta(client, phone, respuesta)
            procesados += 1
        except Exception as e:
            logger.error(f"❌ Error procesando mensaje {msg_id}: {e}")
            enviar_respuesta(client, phone,
                "Lo siento, ha habido un error. Por favor inténtalo de nuevo.")

    logger.info(f"✔ Listo. {procesados} mensaje(s) procesados.")


if __name__ == "__main__":
    main()
