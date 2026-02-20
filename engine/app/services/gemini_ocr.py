"""
NUX IA - Servicio OCR de apuntes manuscritos con Gemini 2.0 Flash Vision.
Extrae texto de imágenes (fotos de apuntes) para alimentar el pipeline de Resumen y Flashcards.
"""

import base64
import logging
import re
from typing import Union

import google.generativeai as genai

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
    """Gemini bloqueó la salida o no detectó texto."""


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
    """Normaliza MIME type para la API de Gemini."""
    m = (mime or "").strip().lower()
    if m in ("image/jpg", "image/jpeg"):
        return "image/jpeg"
    if m in ("image/png", "image/webp", "image/gif"):
        return m
    return "image/jpeg"


def _clean_extracted_text(raw: str) -> str:
    """Limpia y formatea el texto extraído por Gemini."""
    if not raw or not isinstance(raw, str):
        return ""
    text = raw.strip()
    # Quitar posibles bloques de markdown o código que Gemini a veces añade
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
    Extrae texto de una imagen (apuntes manuscritos) usando Gemini 2.0 Flash Vision.

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
    if not settings.GEMINI_API_KEY:
        raise OCRException(
            "GEMINI_API_KEY no configurada. Añádela a .env para usar OCR de apuntes."
        )

    # Normalizar entrada a bytes
    if isinstance(image_input, str):
        try:
            image_bytes = base64.b64decode(image_input, validate=True)
        except Exception as e:
            logger.warning("OCR: base64 decode failed: %s", e)
            raise OCRInvalidImage("Datos de imagen en base64 no válidos.") from e
    else:
        image_bytes = image_input

    if not image_bytes:
        raise OCRInvalidImage("No se recibieron datos de imagen.")

    _check_image_constraints(image_bytes, mime_type)
    mime = _normalize_mime(mime_type)

    try:
        genai.configure(api_key=settings.GEMINI_API_KEY)
    except Exception as e:
        logger.error("OCR: Gemini configure failed: %s", e)
        raise OCRException("Error al configurar la API de Gemini.") from e

    model = genai.GenerativeModel(settings.GEMINI_OCR_MODEL)

    # Contenido: imagen (inline_data) + prompt. Formato estándar google-generativeai.
    image_part = {"inline_data": {"mime_type": mime, "data": image_bytes}}

    try:
        response = model.generate_content(
            [image_part, OCR_PROMPT],
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=settings.MAX_TOKENS,
            ),
        )
    except Exception as e:
        err_msg = str(e).lower()
        logger.exception("OCR: Gemini API error: %s", e)
        if "quota" in err_msg or "429" in err_msg:
            raise OCRException("Límite de uso de la API de Gemini alcanzado. Intenta más tarde.") from e
        if "invalid" in err_msg or "400" in err_msg or "413" in err_msg:
            raise OCRInvalidImage("La imagen no pudo ser procesada por el modelo.") from e
        raise OCRException(f"Error al procesar la imagen: {e}") from e

    if not response or not response.candidates:
        raise OCRBlockedOrEmpty("No se obtuvo respuesta del modelo. La imagen puede estar vacía o ser inadecuada.")

    candidate = response.candidates[0]
    if candidate.finish_reason and "safety" in str(candidate.finish_reason).lower():
        raise OCRBlockedOrEmpty("La imagen no pudo ser analizada por restricciones de contenido.")

    # Acceso al texto: response.text (conveniente) o candidate.content.parts[0].text
    raw = None
    if hasattr(response, "text") and response.text:
        raw = response.text.strip()
    if not raw and candidate.content and getattr(candidate.content, "parts", None):
        parts = candidate.content.parts
        if parts and getattr(parts[0], "text", None):
            raw = parts[0].text.strip()
    if not raw:
        raise OCRBlockedOrEmpty("No se detectó texto en la imagen.")
    if "[IMAGEN_ILEGIBLE]" in raw.upper() or not raw:
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
