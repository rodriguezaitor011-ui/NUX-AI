"""
NUX IA - Servicio OCR de apuntes manuscritos con OpenAI Vision.
Extrae texto de imágenes (fotos de apuntes) para alimentar el pipeline de Resumen y Flashcards.
"""

import base64
import logging
import re
from typing import Union

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)


# Errores específicos para el cliente
class OCRException(Exception):
    """Base para errores del servicio OCR."""


class OCRImageTooLarge(OCRException):
    """Imagen supera el tamaño máximo permitido."""


class OCRInvalidImage(OCRException):
    """Imagen corrupta, formato no soportado o no es una imagen válida."""


class OCRLowQuality(OCRException):
    """Imagen borrosa, mal enfocada o ilegible."""


class OCRBlockedOrEmpty(OCRException):
    """OpenAI bloqueó la salida o no detectó texto."""


# Prompt optimizado para caligrafía manuscrita y apuntes
OCR_PROMPT = """Eres un experto en transcripción de apuntes manuscritos.
Extrae TODO el texto visible en la imagen, respetando:
- Orden de lectura natural (izquierda a derecha, arriba a abajo).
- Saltos de línea y párrafos cuando sea evidente.
- No inventes contenido que no veas; si algo es ilegible, indica [ilegible] o omítelo.
- Mantén números, fórmulas y listas cuando sean claros.
- Devuelve ÚNICAMENTE el texto extraído, sin comentarios ni explicaciones.
- Si la imagen está borrosa, vacía o no contiene texto manuscrito, responde exactamente: [IMAGEN_ILEGIBLE]."""


def _normalize_mime(mime: str) -> str:
    """Normaliza MIME type para la API de OpenAI."""
    m = (mime or "").strip().lower()
    if m in ("image/jpg", "image/jpeg"):
        return "image/jpeg"
    if m in ("image/png", "image/webp", "image/gif"):
        return m
    return "image/jpeg"


def _clean_extracted_text(raw: str) -> str:
    """Limpia y formatea el texto extraído por OpenAI."""
    if not raw or not isinstance(raw, str):
        return ""
    text = raw.strip()
    # Quitar posibles bloques de markdown o código que OpenAI a veces añade
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    # Normalizar saltos de línea múltiples
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _check_image_constraints(image_bytes: bytes, mime_type: str) -> None:
    """Valida tamaño y tipo antes de llamar a la API."""
    if len(image_bytes) > settings.OCR_MAX_IMAGE_SIZE:
        raise OCRImageTooLarge(
            f"La imagen supera el tamaño máximo permitido ({settings.OCR_MAX_IMAGE_SIZE // (1024*1024)} MB)."
        )
    mime = _normalize_mime(mime_type)
    if mime not in settings.OCR_ALLOWED_MIME_TYPES:
        raise OCRInvalidImage(
            f"Formato no permitido. Usa: {', '.join(settings.OCR_ALLOWED_MIME_TYPES)}"
        )
    if len(image_bytes) < 100:
        raise OCRInvalidImage("El archivo es demasiado pequeño para ser una imagen válida.")


def extract_text_from_image(
    image_input: Union[bytes, str],
    mime_type: str = "image/jpeg",
) -> str:
    """
    Extrae texto de una imagen (apuntes manuscritos) usando OpenAI Vision.

    Args:
        image_input: Imagen como bytes o string base64.
        mime_type: MIME type (image/jpeg, image/png, image/webp, image/gif).

    Returns:
        Texto extraído y formateado.

    Raises:
        OCRImageTooLarge: Imagen demasiado grande.
        OCRInvalidImage: Archivo corrupto o formato no soportado.
        OCRLowQuality: Imagen borrosa o ilegible.
        OCRBlockedOrEmpty: No se detectó texto o la respuesta fue bloqueada.
    """
    if not settings.OPENAI_API_KEY:
        raise OCRException(
            "OPENAI_API_KEY no configurada. Añádela a .env para usar OCR de apuntes."
        )

    # Normalizar entrada a bytes (base64 si es string)
    if isinstance(image_input, str):
        try:
            image_bytes = base64.b64decode(image_input, validate=True)
            base64_str = image_input
        except Exception as e:
            logger.warning("OCR: base64 decode failed: %s", e)
            raise OCRInvalidImage("Datos de imagen en base64 no válidos.") from e
    else:
        image_bytes = image_input
        base64_str = base64.b64encode(image_bytes).decode('utf-8')

    if not image_bytes:
        raise OCRInvalidImage("No se recibieron datos de imagen.")

    _check_image_constraints(image_bytes, mime_type)
    mime = _normalize_mime(mime_type)

    try:
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
    except Exception as e:
        logger.error("OCR: OpenAI client initialization failed: %s", e)
        raise OCRException("Error al configurar la API de OpenAI.") from e

    try:
        response = client.chat.completions.create(
            model=settings.OPENAI_OCR_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": OCR_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,{base64_str}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=settings.MAX_TOKENS,
            temperature=0.1
        )
    except Exception as e:
        err_msg = str(e).lower()
        logger.exception("OCR: OpenAI API error: %s", e)
        if "quota" in err_msg or "429" in err_msg or "rate_limit" in err_msg:
            raise OCRException("Límite de uso de la API de OpenAI alcanzado. Intenta más tarde.") from e
        if "invalid" in err_msg or "400" in err_msg or "413" in err_msg:
            raise OCRInvalidImage("La imagen no pudo ser procesada por el modelo.") from e
        raise OCRException(f"Error al procesar la imagen: {e}") from e

    if not response or not response.choices:
        raise OCRBlockedOrEmpty("No se obtuvo respuesta del modelo. La imagen puede estar vacía o ser inadecuada.")

    raw = response.choices[0].message.content

    if not raw:
        raise OCRBlockedOrEmpty("No se detectó texto en la imagen.")
    if "[IMAGEN_ILEGIBLE]" in raw.upper():
        raise OCRLowQuality(
            "La imagen está borrosa, mal enfocada o no contiene texto legible. Prueba con una foto más nítida."
        )

    return _clean_extracted_text(raw)


async def ocr_image_async(
    image_input: Union[bytes, str],
    mime_type: str = "image/jpeg",
) -> str:
    """
    Versión asíncrona que ejecuta el OCR en un thread para no bloquear el event loop.
    """
    import asyncio
    return await asyncio.to_thread(
        extract_text_from_image,
        image_input,
        mime_type,
    )
