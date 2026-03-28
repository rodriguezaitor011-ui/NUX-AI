"""
NUX IA - Sistema de Orquestación NXUS o.0.1 MEJORADO
Prompts optimizados para respuestas más detalladas y útiles
"""

import logging
import asyncio
import json
from typing import Optional, List, Dict, Tuple
from groq import AsyncGroq
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class ModelOrchestrator:
    """Orquestador inteligente de modelos según la tarea"""
    
    MODELS = {
        "structure_analyst": "llama-3.1-8b-instant",  
        "context_manager": "llama-3.3-70b-versatile",
        "chief_editor": "llama-3.3-70b-versatile",    
        "tutor": "deepseek-chat",                      
    }
    
    CONTEXT_THRESHOLD = 25000
    CHUNK_SIZE = 20000
    MAX_TOKENS_PER_REQUEST = 80000
    
    def __init__(self):
        self.groq_client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        self.deepseek_client = httpx.AsyncClient(
            base_url="https://api.deepseek.com",
            headers={
                "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            },
            timeout=60.0
        )
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.deepseek_client.aclose()
    
    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4
    
    def split_into_chunks(self, text: str, chunk_size_tokens: int) -> List[str]:
        chunk_size_chars = chunk_size_tokens * 4
        paragraphs = text.split('\n\n')
        
        chunks = []
        current_chunk = ""
        
        for paragraph in paragraphs:
            if len(current_chunk) + len(paragraph) > chunk_size_chars:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = paragraph
            else:
                current_chunk += "\n\n" + paragraph if current_chunk else paragraph
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        logger.info(f"📑 Documento dividido en {len(chunks)} chunks")
        return chunks
    
    async def _call_groq(
        self, 
        model: str, 
        messages: List[Dict],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        retries: int = 3
    ) -> Optional[str]:
        for attempt in range(retries):
            try:
                response = await self.groq_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature
                )
                return response.choices[0].message.content
            except Exception as e:
                error_str = str(e).lower()
                if ("rate_limit" in error_str or "413" in error_str or "payload too large" in error_str) and attempt < retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Rate limit/size error, waiting {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                logger.error(f"Groq error on attempt {attempt + 1}: {e}")
                if attempt == retries - 1:
                    return None
        return None
    
    async def _call_deepseek(
        self,
        messages: List[Dict],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        stream: bool = False
    ) -> Optional[str]:
        try:
            payload = {
                "model": "deepseek-chat",
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": stream
            }
            
            response = await self.deepseek_client.post("/v1/chat/completions", json=payload)
            response.raise_for_status()
            
            data = response.json()
            return data["choices"][0]["message"]["content"]
            
        except Exception as e:
            logger.error(f"DeepSeek error: {e}")
            return None
    
    async def analyze_structure(self, text: str) -> Optional[Dict]:
        """
        FASE 1: Analista de Estructura (Llama 4 Scout) - MEJORADO
        """
        logger.info("🔍 Fase 1: Analizando estructura con Llama 4 Scout...")
        
        prompt = """Eres un analista experto en estructura de documentos académicos y técnicos.

Analiza el texto y genera un mapa conceptual DETALLADO en formato JSON.

Tu análisis debe incluir:
1. **Tema principal**: Una frase descriptiva y específica
2. **Conceptos clave**: Lista de 8-12 conceptos fundamentales ordenados por importancia
3. **Estructura**: Las secciones principales del documento
4. **Tipo de contenido**: (académico, técnico, narrativo, instructivo, científico)
5. **Complejidad**: (básica, intermedia, avanzada, experta)
6. **Audiencia objetivo**: (estudiante secundaria, universitario, profesional, general)
7. **Palabras clave**: Términos técnicos o específicos del dominio

Formato JSON requerido:
{
  "tema_principal": "string descriptivo",
  "conceptos_clave": ["concepto1", "concepto2", ...],
  "estructura": ["sección1", "sección2", ...],
  "tipo_contenido": "string",
  "complejidad": "string",
  "audiencia": "string",
  "palabras_clave": ["término1", "término2", ...],
  "contexto": "breve contexto del tema (1-2 frases)"
}

Responde SOLO con el JSON, sin explicaciones adicionales."""

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text[:8000]}
        ]
        
        response = await self._call_groq(
            model=self.MODELS["structure_analyst"],
            messages=messages,
            max_tokens=1500,
            temperature=0.3
        )
        
        if response:
            try:
                json_str = response.strip()
                if json_str.startswith("```json"):
                    json_str = json_str.split("```json")[1].split("```")[0]
                elif json_str.startswith("```"):
                    json_str = json_str.split("```")[1].split("```")[0]
                
                structure = json.loads(json_str.strip())
                logger.info(f"✅ Estructura analizada: {structure.get('tema_principal', 'N/A')}")
                return structure
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing JSON structure: {e}")
                return None
        return None
    
    async def process_chunk(self, chunk: str, chunk_num: int, total_chunks: int, structure: Dict) -> Optional[str]:
        logger.info(f"📄 Procesando chunk {chunk_num}/{total_chunks}...")
        
        prompt = f"""Eres un experto en destilación de información académica.

Este es el chunk {chunk_num} de {total_chunks} de: "{structure.get('tema_principal', 'documento')}"

Conceptos clave del documento completo: {', '.join(structure.get('conceptos_clave', [])[:5])}

Tu tarea:
1. Resume SOLO este fragmento preservando:
   - Datos específicos (fechas, nombres, cifras)
   - Conceptos técnicos importantes
   - Relaciones causales o secuenciales
   - Ejemplos relevantes

2. Mantén un tono académico pero claro
3. Máximo 400 palabras
4. Usa bullets si ayuda a la claridad

NO inventes información. Si este chunk no es relevante para los conceptos clave, di "Chunk de contexto secundario" y resume brevemente."""

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": chunk}
        ]
        
        summary = await self._call_groq(
            model=self.MODELS["context_manager"],
            messages=messages,
            max_tokens=2000,
            temperature=0.5
        )
        
        if summary:
            logger.info(f"✅ Chunk {chunk_num} resumido")
        
        return summary
    
    async def process_with_chunking(self, text: str, structure: Dict) -> Optional[str]:
        tokens = self.estimate_tokens(text)
        
        if tokens < self.CONTEXT_THRESHOLD:
            logger.info(f"⏭️ Texto pequeño ({tokens} tokens), sin chunking")
            return text
        
        if tokens < self.MAX_TOKENS_PER_REQUEST:
            logger.info(f"📚 Texto mediano ({tokens} tokens), compresión directa...")
            return await self.compress_medium_document(text, structure)
        
        logger.info(f"🗂️ Texto GRANDE ({tokens} tokens), usando chunking...")
        
        chunks = self.split_into_chunks(text, self.CHUNK_SIZE)
        
        chunk_summaries = []
        for i in range(0, len(chunks), 3):
            batch = chunks[i:i+3]
            tasks = [
                self.process_chunk(chunk, i+j+1, len(chunks), structure)
                for j, chunk in enumerate(batch)
            ]
            results = await asyncio.gather(*tasks)
            chunk_summaries.extend([r for r in results if r])
        
        combined = "\n\n---\n\n".join(chunk_summaries)
        logger.info(f"✅ {len(chunks)} chunks procesados. Texto unificado: {len(combined)} chars")
        
        return combined
    
    async def compress_medium_document(self, text: str, structure: Dict) -> Optional[str]:
        prompt = f"""Eres un experto en síntesis académica.

Documento: {structure.get('tema_principal', 'N/A')}
Tipo: {structure.get('tipo_contenido', 'general')}
Complejidad: {structure.get('complejidad', 'intermedia')}

Conceptos clave a preservar:
{json.dumps(structure.get('conceptos_clave', []), indent=2)}

Tu tarea: Crear una versión condensada (60% más corta) que preserve:
1. TODOS los conceptos de la lista
2. Datos específicos y cifras exactas
3. Relaciones causales importantes
4. Ejemplos clave (no todos)
5. Estructura lógica del contenido

Eliminando:
- Redundancias y repeticiones
- Ejemplos secundarios
- Contexto excesivo
- Transiciones innecesarias

Mantén un tono profesional y académico."""

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text}
        ]
        
        compressed = await self._call_groq(
            model=self.MODELS["context_manager"],
            messages=messages,
            max_tokens=8000,
            temperature=0.5
        )
        
        if compressed:
            logger.info(f"✅ Documento comprimido: {len(compressed)} chars")
        
        return compressed or text
    
    async def generate_summary(self, text: str, structure: Dict, modo: str = "general") -> Optional[str]:
        """
        FASE 2b: Redactor Jefe (Llama 3.3 70B) - MEJORADO
        """
        logger.info(f"✍️ Fase 2b: Redactando resumen con Llama 3.3 70B [modo: {modo}]...")
        
        SUMMARY_PROMPTS = {
            "general": """Resumen académico completo y estructurado.

Formato requerido:
1. **Introducción** (1-2 frases contextuales)
2. **Conceptos Principales** (desarrollo de cada concepto clave)
3. **Puntos Destacados** (datos, cifras, fechas relevantes)
4. **Conclusión o Síntesis** (integración final)

Longitud: 600-1000 palabras
Tono: Académico pero accesible
Usa bullets solo cuando mejore la claridad""",

            "estudiar": """Resumen optimizado para ESTUDIAR y MEMORIZAR.

Estructura obligatoria:

## 📚 Conceptos Fundamentales
[Lista numerada de 5-8 conceptos con definición breve]

## 🎯 Ideas Principales
[Desarrollo de cada idea con ejemplos]

## 📊 Datos y Cifras Clave
[Lista de datos específicos a recordar]

## 💡 Puntos de Examen
[Lo más probable que caiga en un test]

## 🔗 Relaciones y Conexiones
[Cómo se relacionan los conceptos entre sí]

Usa emojis para facilitar escaneo visual.
Longitud: 700-1000 palabras""",

            "corto": """Resumen ejecutivo ULTRA-BREVE.

Formato:
- **Tema**: [1 frase]
- **Puntos clave**: [3-5 bullets]
- **Conclusión**: [1 frase]

Máximo: 150 palabras
Solo lo absolutamente esencial""",

            "profesional": """Resumen profesional para entornos corporativos.

Estructura:
**Executive Summary**: [2-3 frases contextuales]

**Key Findings**: 
- [Hallazgo 1]
- [Hallazgo 2]
- [Hallazgo 3]

**Implications**: [Qué significa esto en la práctica]

**Recommendations** (si aplica): [Acciones sugeridas]

Tono: Formal, conciso, orientado a acción
Longitud: 400-600 palabras"""
        }
        
        context_info = f"""
Contexto del documento:
- Tema: {structure.get('tema_principal', 'N/A')}
- Tipo: {structure.get('tipo_contenido', 'general')}
- Complejidad: {structure.get('complejidad', 'intermedia')}
- Audiencia: {structure.get('audiencia', 'general')}
- Palabras clave: {', '.join(structure.get('palabras_clave', [])[:8])}

Estructura original del documento:
{json.dumps(structure.get('estructura', []), indent=2)}

Conceptos clave que DEBES cubrir:
{json.dumps(structure.get('conceptos_clave', []), indent=2)}
"""

        prompt = f"""Eres un redactor académico experto especializado en síntesis de contenido educativo.

{context_info}

INSTRUCCIONES:
{SUMMARY_PROMPTS.get(modo, SUMMARY_PROMPTS['general'])}

NORMAS ESTRICTAS:
✓ Basa tu resumen ÚNICAMENTE en el contenido proporcionado
✓ Mantén datos exactos (fechas, cifras, nombres propios)
✓ Cubre TODOS los conceptos de la lista de "conceptos_clave"
✓ Usa lenguaje claro pero mantén precisión técnica
✓ NO inventes información
✓ Si hay ambigüedad, indícala explícitamente

Tu resumen debe ser tan útil que el estudiante pueda estudiar SOLO con él."""

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Contenido a resumir:\n\n{text[:70000]}"}
        ]
        
        summary = await self._call_groq(
            model=self.MODELS["chief_editor"],
            messages=messages,
            max_tokens=3500,
            temperature=0.6
        )
        
        if summary:
            logger.info(f"✅ Resumen generado: {len(summary)} caracteres")
        
        return summary
    
    async def generate_flashcards(self, summary: str, structure: Dict) -> Optional[str]:
        """
        FASE 3: Tutor (DeepSeek v3) - MEJORADO
        """
        logger.info("🎴 Fase 3: Generando flashcards con DeepSeek v3...")
        
        prompt = f"""Eres un profesor experto creando flashcards de calidad para estudiantes.

TEMA: {structure.get('tema_principal', 'N/A')}
COMPLEJIDAD: {structure.get('complejidad', 'intermedia')}

Conceptos que debes cubrir (en orden de importancia):
{json.dumps(structure.get('conceptos_clave', []), indent=2)}

INSTRUCCIONES PARA FLASHCARDS DE CALIDAD:

1. **Cantidad**: Genera 12-15 tarjetas
2. **Cobertura**: Asegúrate de cubrir TODOS los conceptos clave
3. **Tipos de preguntas**:
   - Definiciones (¿Qué es...?)
   - Comparaciones (¿En qué se diferencia X de Y?)
   - Aplicaciones (¿Cuándo se usa...?)
   - Relaciones (¿Cómo se relaciona X con Y?)
   - Datos específicos (fechas, cifras, nombres)

4. **Formato EXACTO** (muy importante):

TARJETA 1
Pregunta: [Pregunta clara y específica]
Respuesta: [Respuesta completa pero concisa, 2-3 frases máximo]

TARJETA 2
Pregunta: [Pregunta clara y específica]
Respuesta: [Respuesta completa pero concisa]

REGLAS:
✓ Preguntas claras y directas
✓ Respuestas precisas (no ambiguas)
✓ Usa datos específicos del contenido
✓ Varía los tipos de pregunta
✓ Ordena por dificultad (fácil → difícil)
✗ NO preguntas vagas o genéricas
✗ NO respuestas de una sola palabra

Empieza ahora:"""

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Contenido base para las flashcards:\n\n{summary}"}
        ]
        
        flashcards = await self._call_deepseek(
            messages=messages,
            max_tokens=3000,
            temperature=0.7
        )
        
        if flashcards:
            logger.info("✅ Flashcards generadas con DeepSeek v3")
        
        return flashcards
    
    async def chat_with_tutor(
        self,
        summary: str,
        structure: Dict,
        question: str,
        history: List[Dict] = None
    ) -> Optional[str]:
        """
        Chat con DeepSeek v3 - MEJORADO
        """
        logger.info("💬 Chat con DeepSeek v3 (contexto mejorado)...")
        
        system_prompt = f"""Eres un tutor académico experto y paciente.

INFORMACIÓN DEL DOCUMENTO:
- Tema: {structure.get('tema_principal', 'N/A')}
- Tipo: {structure.get('tipo_contenido', 'general')}
- Nivel: {structure.get('complejidad', 'intermedia')}
- Audiencia: {structure.get('audiencia', 'estudiante')}

CONCEPTOS CLAVE DEL DOCUMENTO:
{', '.join(structure.get('conceptos_clave', [])[:10])}

CONTENIDO COMPLETO (tu fuente de verdad):
{summary}

---

TU ROL COMO TUTOR:
1. **Responde basándote SOLO en el contenido proporcionado**
2. **Si la pregunta no se puede responder con la info disponible**, dilo claramente
3. **Sé pedagógico**: explica con claridad, usa ejemplos del propio documento
4. **Adapta tu lenguaje** al nivel de complejidad del material
5. **Si detectas confusión**, haz preguntas aclaratorias
6. **Conecta conceptos** cuando sea relevante

FORMATO DE RESPUESTAS:
- Respuestas completas (3-6 frases normalmente)
- Usa bullets si ayuda a la claridad
- Cita datos específicos del documento cuando sea relevante
- Si es un concepto complejo, divídelo en partes

Sé conciso pero completo. Tu objetivo es que el estudiante ENTIENDA, no solo que tenga información."""

        messages = [{"role": "system", "content": system_prompt}]
        
        if history:
            for item in history[-5:]:
                messages.append({"role": "user", "content": item["pregunta"]})
                messages.append({"role": "assistant", "content": item["respuesta"]})
        
        messages.append({"role": "user", "content": question})
        
        response = await self._call_deepseek(
            messages=messages,
            max_tokens=1500,
            temperature=0.6
        )
        
        if response:
            logger.info("✅ Respuesta generada")
        
        return response

    async def generate_mindmap(self, summary: str, structure: Dict) -> Optional[str]:
        """
        Genera un mapa mental en formato Mermaid desde el resumen
        """
        logger.info("🗺️ Generando mapa mental con DeepSeek v3...")
        
        prompt = f"""Eres un experto en crear mapas mentales educativos.

TEMA: {structure.get('tema_principal', 'N/A')}
CONCEPTOS CLAVE: {', '.join(structure.get('conceptos_clave', [])[:8])}

Tu tarea: Crear un mapa mental en formato Mermaid que organice visualmente los conceptos principales.

REGLAS ESTRICTAS:
1. Usa SOLO sintaxis Mermaid válida
2. Máximo 20 nodos (no más)
3. Organiza jerárquicamente: tema principal → subtemas → detalles
4. Usa nombres cortos (máx 4 palabras por nodo)
5. NO uses caracteres especiales problemáticos: paréntesis, corchetes, comillas
6. Usa solo letras, números, espacios y guiones

FORMATO REQUERIDO:

```mermaid
mindmap
  root((Tema Principal))
    Concepto 1
      Detalle A
      Detalle B
    Concepto 2
      Detalle C
      Detalle D
    Concepto 3
      Detalle E
```

EJEMPLO:

```mermaid
mindmap
  root((Fotosíntesis))
    Fase Luminosa
      Tilacoides
      Fotosistemas
      ATP y NADPH
    Fase Oscura
      Estroma
      Ciclo de Calvin
      Glucosa
    Factores
      Luz solar
      CO2
      Agua
```

Genera SOLO el código Mermaid, sin explicaciones adicionales.
Empieza con ```mermaid y termina con ```
"""

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Contenido para el mapa mental:\n\n{summary[:5000]}"}
        ]
        
        mindmap = await self._call_deepseek(
            messages=messages,
            max_tokens=2000,
            temperature=0.7
        )
        
        if mindmap:
            # Limpiar el código Mermaid
            mindmap = mindmap.strip()
            if mindmap.startswith("```mermaid"):
                mindmap = mindmap.split("```mermaid")[1].split("```")[0].strip()
            elif mindmap.startswith("```"):
                mindmap = mindmap.split("```")[1].split("```")[0].strip()
            
            logger.info("✅ Mapa mental generado")
        
        return mindmap


# Pipeline completo (sin cambios en la interfaz)
async def process_document_pipeline(
    text: str,
    modo: str = "general",
    task: str = "summary"
) -> Tuple[Optional[str], Optional[Dict], Optional[str]]:
    async with ModelOrchestrator() as orchestrator:
        try:
            structure = await orchestrator.analyze_structure(text)
            if not structure:
                return None, None, "Error al analizar la estructura del documento"
            
            compressed_text = await orchestrator.process_with_chunking(text, structure)
            if task == "mindmap":
                summary = await orchestrator.generate_summary(compressed_text, structure, "general")
                if not summary:
                    return None, structure, "Error al generar resumen base"
                
                mindmap = await orchestrator.generate_mindmap(summary, structure)
                if not mindmap:
                    return None, structure, "Error al generar mapa mental"
                
                return mindmap, structure, None
            
            elif task == "flashcards":
                summary = await orchestrator.generate_summary(compressed_text, structure, "estudiar")
                if not summary:
                    return None, structure, "Error al generar resumen base"
                
                flashcards = await orchestrator.generate_flashcards(summary, structure)
                if not flashcards:
                    return None, structure, "Error al generar flashcards"
                
                return flashcards, structure, None
            
            else:
                summary = await orchestrator.generate_summary(compressed_text, structure, modo)
                if not summary:
                    return None, structure, "Error al generar resumen"
                
                return summary, structure, None
                
        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            return None, None, f"Error en el pipeline: {str(e)}"


# ai_orchestrator.py
# REEMPLAZAR la función chat_with_document al final del archivo

async def chat_with_document(
    question: str,
    document_context: Optional[Dict] = None,
    mode: str = "sources",
    history: List[Dict] = None
) -> str:
    """
    Wrapper público para el chat.
    Acepta el doc_context como dict con keys: summary, structure, original_text
    Retorna string directamente (no tuple).
    """
    async with ModelOrchestrator() as orchestrator:
        try:
            if mode == "general" or not document_context:
                # Sin contexto de documento: responder como asistente general
                response = await orchestrator._call_deepseek(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Eres NUX IA, un asistente académico experto. "
                                "Responde de forma clara, precisa y educativa. "
                                "Usa Markdown para formatear tus respuestas."
                            )
                        },
                        {"role": "user", "content": question}
                    ],
                    max_tokens=1500,
                    temperature=0.7
                )
                return response or "No pude generar una respuesta."

            # Extraer summary y structure del context dict
            summary = document_context.get("summary", "")
            structure = document_context.get("structure", {})

            if not summary or not structure:
                return (
                    "No hay documentos procesados en esta sesión. "
                    "Usa una herramienta primero (Resumir, Analizar) para procesar tus fuentes."
                )

            response = await orchestrator.chat_with_tutor(
                summary=summary,
                structure=structure,
                question=question,
                history=history or []
            )

            return response or "No pude generar una respuesta sobre el documento."

        except Exception as e:
            logger.error(f"chat_with_document error: {e}", exc_info=True)
            return f"Error al procesar la pregunta: {str(e)}"