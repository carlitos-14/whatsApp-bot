# Bot de WhatsApp — Twilio Sandbox

## Variables de entorno (configurar en Koyeb)

| Variable | Descripción |
|---|---|
| `GROQ_API_KEY` | Tu API key de Groq |
| `SUPABASE_URL` | URL del proyecto Supabase |
| `SUPABASE_KEY` | Anon Key del proyecto Supabase |
| `GMAIL_CREDENTIALS_JSON` | JSON con token de Google |
| `GOOGLE_CALENDAR_ID` | ID del calendario (o "primary") |
| `COMPANY_NAME` | Nombre de tu empresa |
| `CONTACT_INFO` | Email o teléfono de contacto para escalados |
| `EVENT_DURATION_MINUTES` | Duración de cada cita en minutos (por defecto 60) |
| `MAX_CITAS_ACTIVAS` | Máximo de citas por cliente (por defecto 2) |

---

## Paso 1 — Crear cuenta en Twilio

1. Ve a twilio.com → Sign up (gratis, sin tarjeta)
2. Ve a Messaging → Try it out → Send a WhatsApp message
3. Twilio te da un número sandbox y un código de activación
4. Tú y tus testers mandan ese código por WhatsApp al número de Twilio para unirse

---

## Paso 2 — Desplegar en Koyeb

1. Sube el código a un repo de GitHub
2. Ve a koyeb.com → New service → GitHub
3. Selecciona el repo y añade las variables de entorno
4. Deploy → obtienes una URL pública (ej: https://tuapp.koyeb.app)

---

## Paso 3 — Configurar webhook en Twilio

1. En Twilio ve a Messaging → Try it out → WhatsApp Sandbox Settings
2. En "When a message comes in" pon: https://tuapp.koyeb.app/webhook
3. Método: POST
4. Guarda

A partir de ahí cualquier mensaje al número sandbox llega a tu bot.

---

## Supabase — crear tabla

Ejecuta el contenido de schema.sql en el SQL Editor de tu proyecto Supabase.
