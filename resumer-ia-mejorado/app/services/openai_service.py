import logging
from typing import Optional, List, Dict
from groq import AsyncGroq
from app.config import settings

logger = logging.getLogger(__name__)

MODOS_PROMPTS = {
    "general": "Resumen claro, equilibrado y bien organizado.",
    "estudiar": """Crea un resumen estructurado para estudiar que incluya:
- Ideas principales numeradas
- Conceptos clave destacados
- Un apartado de 'Puntos importantes a recordar'
Hazlo fácil de memorizar.""",
    "corto": "Resumen muy breve en 3-5 frases. Solo lo esencial, sin detalles.",
    "profesional": "Resumen formal y conciso, lenguaje técnico y profesional, ideal para entornos de trabajo.",
    "ninos": "Explica el texto de forma muy simple, como si se lo contaras a un niño de 10 años. Usa frases cortas y palabras fáciles.",
    "preguntas": """No hagas un resumen. En su lugar, genera 5-8 preguntas de examen sobre el texto.
Formato:
1. ¿Pregunta?
2. ¿Pregunta?
...
Incluye preguntas de distintos tipos: comprensión, análisis y reflexión.""",
    "flashcards": """No hagas un resumen. Genera 10-15 flashcards (tarjetas de estudio) en este formato EXACTO:

TARJETA 1
Pregunta: [Concepto clave o pregunta corta]
Respuesta: [Explicación clara y concisa]

TARJETA 2
Pregunta: [Otro concepto]
Respuesta: [Explicación]

[... y así sucesivamente]

Las flashcards deben cubrir los conceptos más importantes del texto. Usa lenguaje claro y directo.""",
}


class AIService:
    """Servicio de IA usando Groq (gratuito y ultrarrápido)"""

    def __init__(self):
        self.client = AsyncGroq(api_key=settings.GROQ_API_KEY)

    async def resumir_texto(
        self,
        texto: str,
        instrucciones: Optional[str] = None,
        modo: str = "general"
    ) -> tuple[Optional[str], Optional[str]]:
        """Genera un resumen del texto según el modo especificado"""
        try:
            prompt = self._construir_prompt(instrucciones, modo)

            logger.info(
                f"Generando resumen con Groq [{settings.GROQ_MODEL}] | "
                f"{len(texto)} caracteres | modo: {modo}"
            )

            respuesta = await self.client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": texto}
                ],
                max_tokens=settings.MAX_TOKENS,
                temperature=settings.TEMPERATURE
            )

            resumen = respuesta.choices[0].message.content
            logger.info(
                f"Resumen generado ✅ | "
                f"Tokens: {respuesta.usage.total_tokens}"
            )
            return resumen, None

        except Exception as e:
            error_str = str(e).lower()

            if "api_key" in error_str or "api key" in error_str:
                error_msg = "API Key de Groq incorrecta. Revisa tu archivo .env"
            elif "rate_limit" in error_str or "429" in error_str:
                error_msg = "Límite de Groq alcanzado. Espera unos segundos."
            else:
                error_msg = "Error al conectar con Groq. Por favor intenta más tarde."

            logger.error(f"Groq error: {e}")
            return None, error_msg

    async def responder_pregunta(
        self,
        texto: str,
        pregunta: str,
        historial: List[Dict[str, str]] = None
    ) -> tuple[Optional[str], Optional[str]]:
        """Responde una pregunta sobre el texto dado"""
        try:
            # Construir historial de mensajes
            messages = [
                {
                    "role": "system",
                    "content": """Eres un asistente experto que responde preguntas sobre textos.
Responde de forma clara, concisa y precisa basándote SOLO en el contenido del texto proporcionado.
Si la pregunta no se puede responder con el texto, dilo claramente."""
                },
                {
                    "role": "user",
                    "content": f"Texto de referencia:\n\n{texto}"
                }
            ]
            
            # Añadir historial si existe
            if historial:
                for item in historial:
                    messages.append({"role": "user", "content": item["pregunta"]})
                    messages.append({"role": "assistant", "content": item["respuesta"]})
            
            # Añadir pregunta actual
            messages.append({"role": "user", "content": pregunta})

            logger.info(f"Respondiendo pregunta sobre texto de {len(texto)} caracteres")

            respuesta = await self.client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=messages,
                max_tokens=500,
                temperature=0.7
            )

            respuesta_texto = respuesta.choices[0].message.content
            logger.info(f"Pregunta respondida ✅")
            return respuesta_texto, None

        except Exception as e:
            logger.error(f"Error al responder pregunta: {e}")
            return None, "Error al procesar la pregunta"

    def _construir_prompt(self, instrucciones: Optional[str], modo: str) -> str:
        """Construye el prompt del sistema según el modo"""
        instruccion_modo = MODOS_PROMPTS.get(modo, MODOS_PROMPTS["general"])
        instruccion_final = instrucciones.strip() if instrucciones and instrucciones.strip() else instruccion_modo

        return f"""Eres un asistente experto en resumir textos de forma clara, precisa y útil.

Instrucciones:
{instruccion_final}

Normas:
- No inventes información
- No añadas opiniones
- Usa un lenguaje natural y directo
- Adapta el nivel al contexto del texto"""


# Instancia singleton
openai_service = AIService()
