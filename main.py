"""
main.py — Servidor webhook para WhatsApp via Twilio Sandbox
"""

import os
import logging
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from bot import procesar_mensaje

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/webhook", methods=["POST"])
def webhook():
    phone  = request.form.get("From", "")   # ej: whatsapp:+34612345678
    texto  = request.form.get("Body", "").strip()
    msg_id = request.form.get("MessageSid", "")

    logger.info(f"📱 Mensaje de {phone}: {texto}")

    respuesta_texto = procesar_mensaje(phone=phone, texto=texto, msg_id=msg_id)

    resp = MessagingResponse()
    resp.message(respuesta_texto)
    return str(resp), 200, {"Content-Type": "text/xml"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
