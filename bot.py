"""
bot.py — Lógica del agente de WhatsApp (Twilio Sandbox)
"""

import os
import re
import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dateutil import parser as dateparser

from groq import Groq
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from supabase import create_client

logger = logging.getLogger(__name__)

TZ = ZoneInfo("Europe/Madrid")

# ── Clientes ───────────────────────────────────────────────────────────────
groq_client  = Groq(api_key=os.environ["GROQ_API_KEY"])
COMPANY      = os.environ.get("COMPANY_NAME", "Nuestra Empresa")
CONTACT_INFO = os.environ.get("CONTACT_INFO", "")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

GOOGLE_CALENDAR_ID     = os.environ.get("GOOGLE_CALENDAR_ID", "primary")
EVENT_DURATION_MINUTES = int(os.environ.get("EVENT_DURATION_MINUTES", "60"))
MAX_CITAS_ACTIVAS      = int(os.environ.get("MAX_CITAS_ACTIVAS", "2"))

# ── Contexto empresa (PDF opcional) ───────────────────────────────────────
COMPANY_CONTEXT = ""
try:
    from pdf_context import load_company_context
    COMPANY_CONTEXT = load_company_context()
except Exception:
    pass

CONTEXT_BLOCK = (
    f"\n\n---\nDOCUMENTACIÓN DE LA EMPRESA:\n{COMPANY_CONTEXT}\n---"
    if COMPANY_CONTEXT else ""
)

# ── Calendario de los próximos 14 días ────────────────────────────────────
_DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_HOY_DT  = datetime.now(tz=TZ)
_HOY     = f"{_DIAS_ES[_HOY_DT.weekday()]} {_HOY_DT.strftime('%d/%m/%Y')}"

def _calendario():
    lines = []
    for i in range(14):
        d = _HOY_DT + timedelta(days=i)
        lines.append(f"  - {_DIAS_ES[d.weekday()]} = {d.strftime('%Y-%m-%d')}")
    return "\n".join(lines)

SYSTEM_PROMPT = f"""Eres el asistente de atención al cliente de {COMPANY} por WhatsApp.
{CONTEXT_BLOCK}

La fecha de hoy es {_HOY}. Calendario de los próximos días:
{_calendario()}

Siempre devuelve fecha_hora en formato YYYY-MM-DDTHH:MM:SS, nunca texto.
Analiza el mensaje y responde SOLO con JSON válido (sin markdown, sin texto extra).

Un objeto:
{{
  "accion": "AGENDAR" | "CANCELAR" | "CANCELAR_TODAS" | "REAGENDAR" | "CONSULTAR" | "RESPONDER" | "ESCALAR",
  "fecha_hora": "YYYY-MM-DDTHH:MM:SS" o null,
  "respuesta_texto": "Texto para enviar al cliente por WhatsApp (informal, cercano, sin saludos largos)"
}}

Reglas de decisión:
- AGENDAR       → el cliente pide una cita con fecha y hora concreta
- CANCELAR      → quiere cancelar una cita. Si menciona el día, ponlo en fecha_hora a las 00:00:00. Si no especifica, fecha_hora es null. NUNCA uses ESCALAR para cancelaciones.
- CANCELAR_TODAS → quiere cancelar todas sus citas. fecha_hora es null.
- REAGENDAR     → quiere cambiar su cita a otra fecha/hora. fecha_hora = nueva fecha solicitada.
- CONSULTAR     → pregunta por disponibilidad sin confirmar cita. fecha_hora = día consultado a las 09:30 si no indica hora.
- RESPONDER     → preguntas sobre servicios, precios, horarios (usa la documentación)
- ESCALAR       → quejas, temas legales, pide hablar con persona humana

IMPORTANTE: Se atiende todos los días de 9:30 a 17:00 incluyendo fines de semana.
SEGURIDAD: Solo gestiona citas del propio número que escribe.
Si la fecha/hora no está clara para AGENDAR o CONSULTAR, usa ESCALAR.
Para CANCELAR, nunca uses ESCALAR aunque la fecha no sea exacta.

En respuesta_texto usa un tono cercano e informal apropiado para WhatsApp.
Para AGENDAR NO menciones fecha ni hora en respuesta_texto, el sistema la añade automáticamente."""


# ══════════════════════════════════════════════════════════════════════════
#  SUPABASE
# ══════════════════════════════════════════════════════════════════════════
def get_db():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def clean_phone(phone: str) -> str:
    """Normaliza número (quita espacios, asegura formato +34xxx)."""
    return phone.strip()


def guardar_cita(phone: str, event_id: str, fecha_cita: datetime):
    try:
        get_db().table("citas").insert({
            "phone": clean_phone(phone),
            "event_id": event_id,
            "fecha_cita": fecha_cita.isoformat(),
        }).execute()
        logger.info(f"💾 Cita guardada para {phone}")
    except Exception as e:
        logger.error(f"❌ Error guardando cita: {e}")


def obtener_ultimo_event_id(phone: str):
    try:
        r = (get_db().table("citas")
             .select("event_id")
             .eq("phone", clean_phone(phone))
             .order("created_at", desc=True)
             .limit(1)
             .execute())
        return r.data[0]["event_id"] if r.data else None
    except Exception as e:
        logger.error(f"❌ Error obteniendo event_id: {e}")
        return None


def obtener_event_id_por_fecha(phone: str, fecha: datetime):
    try:
        if fecha.hour == 0 and fecha.minute == 0:
            desde = fecha.replace(hour=0, minute=0, second=0).isoformat()
            hasta = fecha.replace(hour=23, minute=59, second=59).isoformat()
        else:
            desde = (fecha - timedelta(hours=2)).isoformat()
            hasta = (fecha + timedelta(hours=2)).isoformat()
        r = (get_db().table("citas")
             .select("event_id")
             .eq("phone", clean_phone(phone))
             .gte("fecha_cita", desde)
             .lte("fecha_cita", hasta)
             .order("fecha_cita")
             .limit(1)
             .execute())
        return r.data[0]["event_id"] if r.data else None
    except Exception as e:
        logger.error(f"❌ Error buscando cita por fecha: {e}")
        return None


def obtener_todas_citas(phone: str):
    try:
        ahora = datetime.now(tz=TZ).isoformat()
        r = (get_db().table("citas")
             .select("event_id, fecha_cita")
             .eq("phone", clean_phone(phone))
             .gt("fecha_cita", ahora)
             .order("fecha_cita")
             .execute())
        return r.data or []
    except Exception as e:
        logger.error(f"❌ Error obteniendo citas: {e}")
        return []


def eliminar_cita(phone: str, event_id: str):
    try:
        (get_db().table("citas")
         .delete()
         .eq("phone", clean_phone(phone))
         .eq("event_id", event_id)
         .execute())
        logger.info(f"🗑️ Cita eliminada de Supabase: {event_id}")
    except Exception as e:
        logger.error(f"❌ Error eliminando cita: {e}")


def contar_citas_futuras(phone: str) -> int:
    try:
        ahora = datetime.now(tz=TZ).isoformat()
        r = (get_db().table("citas")
             .select("event_id", count="exact")
             .eq("phone", clean_phone(phone))
             .gt("fecha_cita", ahora)
             .execute())
        return r.count if r.count is not None else len(r.data)
    except Exception:
        return 0


# ══════════════════════════════════════════════════════════════════════════
#  GOOGLE CALENDAR
# ══════════════════════════════════════════════════════════════════════════
def get_calendar_service():
    creds_data = json.loads(os.environ["GMAIL_CREDENTIALS_JSON"])
    scopes = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/calendar",
    ]
    creds = Credentials(
        token=creds_data.get("token"),
        refresh_token=creds_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=creds_data.get("client_id"),
        client_secret=creds_data.get("client_secret"),
        scopes=scopes,
    )
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
    return build("calendar", "v3", credentials=creds)


def slot_disponible(fecha: datetime) -> bool:
    try:
        svc = get_calendar_service()
        fin = (fecha + timedelta(minutes=EVENT_DURATION_MINUTES)).isoformat()
        eventos = svc.events().list(
            calendarId=GOOGLE_CALENDAR_ID,
            timeMin=fecha.isoformat(),
            timeMax=fin,
            singleEvents=True,
        ).execute().get("items", [])
        return len(eventos) == 0
    except Exception as e:
        logger.error(f"❌ Error comprobando slot: {e}")
        return False


def buscar_slots_libres(ref: datetime, n=3):
    HORA_INICIO, MIN_INICIO, HORA_FIN = 9, 30, 17
    ahora = datetime.now(tz=ref.tzinfo)
    punto = max(ahora, ref)
    punto = punto.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    slots = []
    candidato = punto
    for _ in range(14 * 8):
        en_horario = (
            (candidato.hour > HORA_INICIO or (candidato.hour == HORA_INICIO and candidato.minute >= MIN_INICIO))
            and candidato.hour < HORA_FIN
        )
        if not en_horario:
            candidato = (candidato + timedelta(days=1)).replace(
                hour=HORA_INICIO, minute=MIN_INICIO, second=0, microsecond=0)
            continue
        if slot_disponible(candidato):
            slots.append(candidato)
            if len(slots) >= n:
                break
        candidato += timedelta(hours=1)
    return slots


def agendar_en_calendar(fecha: datetime, phone: str) -> str | None:
    if not slot_disponible(fecha):
        return None
    try:
        svc = get_calendar_service()
        fin = fecha + timedelta(minutes=EVENT_DURATION_MINUTES)
        evento = {
            "summary": f"Cita WhatsApp: {phone}",
            "description": f"Cita agendada por WhatsApp para {phone}.",
            "start": {"dateTime": fecha.isoformat(), "timeZone": "Europe/Madrid"},
            "end":   {"dateTime": fin.isoformat(),   "timeZone": "Europe/Madrid"},
            "reminders": {"useDefault": False, "overrides": [
                {"method": "email",  "minutes": 24 * 60},
                {"method": "popup",  "minutes": 30},
            ]},
        }
        r = svc.events().insert(
            calendarId=GOOGLE_CALENDAR_ID,
            body=evento,
            sendUpdates="all",
        ).execute()
        return r.get("id")
    except Exception as e:
        logger.error(f"❌ Error agendando en Calendar: {e}")
        return None


def cancelar_en_calendar(event_id: str) -> bool:
    try:
        svc = get_calendar_service()
        svc.events().delete(
            calendarId=GOOGLE_CALENDAR_ID,
            eventId=event_id,
            sendUpdates="all",
        ).execute()
        return True
    except Exception as e:
        logger.error(f"❌ Error cancelando en Calendar: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════
#  GROQ — analizar mensaje
# ══════════════════════════════════════════════════════════════════════════
def analizar(texto: str) -> dict:
    for _ in range(3):
        try:
            resp = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": texto},
                ],
                temperature=0.1,
                max_tokens=500,
            )
            raw = resp.choices[0].message.content.strip()
            raw = re.sub(r"^```json|^```|```$", "", raw, flags=re.MULTILINE).strip()
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"⚠️ Reintento Groq: {e}")
    return {"accion": "ESCALAR", "fecha_hora": None,
            "respuesta_texto": "Lo siento, ha habido un error. Por favor contáctanos directamente."}


def fmt_fecha(dt: datetime) -> str:
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    return f"{dias[dt.weekday()]} {dt.strftime('%d/%m/%Y')} a las {dt.strftime('%H:%M')}"


# ══════════════════════════════════════════════════════════════════════════
#  PROCESADOR PRINCIPAL — devuelve el texto a enviar al cliente
# ══════════════════════════════════════════════════════════════════════════
def procesar_mensaje(phone: str, texto: str, msg_id: str) -> str:
    decision = analizar(texto)
    accion   = decision.get("accion", "ESCALAR").upper()
    fh_str   = decision.get("fecha_hora")
    respuesta = decision.get("respuesta_texto", "")

    logger.info(f"🤖 Decisión para {phone}: {accion} | fecha_hora: {fh_str}")

    fecha = None
    if fh_str:
        try:
            fecha = dateparser.parse(fh_str).replace(tzinfo=TZ)
        except Exception:
            pass

    if accion == "AGENDAR":
        if not fecha:
            return "No he podido entender la fecha y hora. ¿Puedes indicarla de forma más concreta?"

        if fecha < datetime.now(tz=TZ):
            return "Esa fecha ya ha pasado. ¿Quieres que te busque un hueco próximo?"

        if contar_citas_futuras(phone) >= MAX_CITAS_ACTIVAS:
            return f"Ya tienes {MAX_CITAS_ACTIVAS} citas pendientes. Cancela una antes de reservar otra."

        event_id = agendar_en_calendar(fecha, phone)
        if not event_id:
            slots = buscar_slots_libres(fecha)
            if slots:
                opciones = "\n".join(f"  • {fmt_fecha(s)}" for s in slots)
                return f"Ese horario no está disponible. Te propongo estas opciones:\n{opciones}"
            return "No hay huecos disponibles en los próximos días. Contáctanos directamente."

        guardar_cita(phone, event_id, fecha)
        return f"{respuesta}\n\n📅 *{fmt_fecha(fecha)}*"

    elif accion == "CANCELAR":
        if fecha:
            event_id = obtener_event_id_por_fecha(phone, fecha)
        else:
            event_id = obtener_ultimo_event_id(phone)

        if not event_id:
            return "No he encontrado ninguna cita para cancelar. ¿Puedes indicarme la fecha?"

        cancelar_en_calendar(event_id)
        eliminar_cita(phone, event_id)
        return respuesta or "✅ Tu cita ha sido cancelada correctamente."

    elif accion == "CANCELAR_TODAS":
        citas = obtener_todas_citas(phone)
        if not citas:
            return "No tienes ninguna cita pendiente."
        for c in citas:
            cancelar_en_calendar(c["event_id"])
            eliminar_cita(phone, c["event_id"])
        return f"✅ Se han cancelado tus {len(citas)} cita(s) pendiente(s)."

    elif accion == "REAGENDAR":
        event_id_actual = obtener_ultimo_event_id(phone)
        if not event_id_actual:
            return "No encontré ninguna cita activa para cambiar. ¿Quieres reservar una nueva?"
        if not fecha:
            return "¿A qué fecha y hora quieres cambiar tu cita?"

        cancelar_en_calendar(event_id_actual)
        eliminar_cita(phone, event_id_actual)

        new_event_id = agendar_en_calendar(fecha, phone)
        if not new_event_id:
            slots = buscar_slots_libres(fecha)
            if slots:
                opciones = "\n".join(f"  • {fmt_fecha(s)}" for s in slots)
                return f"Ese horario no está libre. Estas son las opciones más cercanas:\n{opciones}"
            return "No hay huecos disponibles cerca de esa fecha."

        guardar_cita(phone, new_event_id, fecha)
        return f"{respuesta}\n\n📅 *{fmt_fecha(fecha)}*"

    elif accion == "CONSULTAR":
        if not fecha:
            return "¿Qué día quieres consultar?"
        slots = buscar_slots_libres(fecha)
        if slots:
            opciones = "\n".join(f"  • {fmt_fecha(s)}" for s in slots)
            return f"Estos son los huecos disponibles:\n{opciones}"
        return "No hay huecos libres ese día. ¿Quieres que te busque en otro momento?"

    elif accion == "RESPONDER":
        return respuesta

    else:  # ESCALAR
        return respuesta or f"Tu consulta necesita atención personalizada. Contáctanos en: {CONTACT_INFO}"
