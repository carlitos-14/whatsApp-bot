"""
pdf_context.py
Extrae texto del PDF de documentación de la empresa para inyectarlo en el SYSTEM_PROMPT.
"""

import logging
import os

logger = logging.getLogger(__name__)

PDF_PATH = os.environ.get("COMPANY_PDF_PATH", "documentacion_empresa.pdf")
MAX_CHARS = 6000


def load_company_context(path: str = PDF_PATH) -> str:
    if not os.path.exists(path):
        logger.warning(f"⚠️ PDF no encontrado en '{path}'. El agente funcionará sin contexto de empresa.")
        return ""

    try:
        import PyPDF2

        text_parts = []
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text.strip())

        full_text = "\n\n".join(text_parts)[:MAX_CHARS]
        logger.info(f"📄 PDF cargado: {len(full_text)} caracteres extraídos de '{path}'.")
        return full_text

    except Exception as e:
        logger.error(f"❌ Error leyendo PDF '{path}': {e}")
        return ""
