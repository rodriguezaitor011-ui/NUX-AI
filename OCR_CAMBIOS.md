# 📄 Migración OCR: Gemini → OpenAI Vision

## 🎯 Resumen de cambios

Se ha reemplazado el servicio de **OCR (Optical Character Recognition) de Gemini** por **OpenAI Vision API** para extraer texto de imágenes de apuntes manuscritos.

---

## ❓ ¿Qué es OCR?

**OCR (Reconocimiento Óptico de Caracteres)** es la capacidad de una IA para:
- 📸 Recibir una imagen (foto de apuntes)
- 🔍 Analizar el contenido visual
- 📝 Extraer el texto manuscrito o impreso
- 💾 Devolver el texto estructurado

En tu aplicación, el OCR permite:
1. Subir una foto de apuntes manuscritos
2. La IA extrae automáticamente el texto
3. El texto se alimenta al pipeline de resumen/flashcards

---

## 🔄 Cambio realizado

### ❌ ANTES: Google Gemini 2.0 Flash Vision
```python
# engine/app/services/gemini_ocr.py (antes)
import google.generativeai as genai

def extract_text_from_image(image_input, mime_type):
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.0-flash")
    response = model.generate_content([image_part, OCR_PROMPT])
```

### ✅ AHORA: OpenAI Vision (GPT-4o)
```python
# engine/app/services/gemini_ocr.py (ahora)
from openai import OpenAI

def extract_text_from_image(image_input, mime_type):
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=settings.OPENAI_OCR_MODEL,
        messages=[...with image data...]
    )
```

---

## 📊 Tabla comparativa

| Aspecto | Gemini 2.0 Flash | OpenAI Vision (GPT-4o) |
|---------|-----------------|------------------------|
| **Proveedor** | Google | OpenAI |
| **Modelo** | gemini-2.0-flash | gpt-4o |
| **API Key** | GEMINI_API_KEY | OPENAI_API_KEY |
| **Libería** | google-generativeai | openai |
| **Formato entrada** | inline_data bytes | base64 data URL |
| **Velocidad** | Media | Rápida |
| **Calidad** | Muy buena | Excelente |
| **Costo** | Gratuito (con límites) | Pago por uso |
| **Precisión manuscrita** | ✅ Buena | ✅ Excelente |

---

## 📝 Cambios técnicos específicos

### 1. **Cambio de librería**

**Antes:**
```python
import google.generativeai as genai
```

**Ahora:**
```python
from openai import OpenAI
```

---

### 2. **Cambio de configuración**

**Antes (config.py):**
```python
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_OCR_MODEL: str = os.getenv("GEMINI_OCR_MODEL", "gemini-2.0-flash")
```

**Ahora (config.py):**
```python
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_OCR_MODEL: str = os.getenv("OPENAI_OCR_MODEL", "gpt-4o")
```

---

### 3. **Cambio del cliente de API**

**Antes:**
```python
genai.configure(api_key=settings.GEMINI_API_KEY)
model = genai.GenerativeModel(settings.GEMINI_OCR_MODEL)

# Formato Gemini
image_part = {"inline_data": {"mime_type": mime, "data": image_bytes}}
response = model.generate_content([image_part, OCR_PROMPT])
```

**Ahora:**
```python
client = OpenAI(api_key=settings.OPENAI_API_KEY)

# Formato OpenAI (conversation chat)
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
    ]
)
```

**Diferencias clave:**
- Gemini: Usa `inline_data` con bytes directos
- OpenAI: Usa `data URI` con base64 en URL

---

### 4. **Cambio de manejo de respuestas**

**Antes (Gemini):**
```python
if not response or not response.candidates:
    raise OCRBlockedOrEmpty(...)

candidate = response.candidates[0]
raw = response.text or candidate.content.parts[0].text
```

**Ahora (OpenAI):**
```python
if not response or not response.choices:
    raise OCRBlockedOrEmpty(...)

raw = response.choices[0].message.content
```

---

### 5. **Cambio en manejo de errores**

**Antes (Gemini):**
```python
except Exception as e:
    if "quota" in error_str or "429" in error_str:
        raise OCRException("Límite de Gemini alcanzado...")
    if "invalid" in error_str or "400" in error_str:
        raise OCRInvalidImage("Gemini no pudo procesar...")
```

**Ahora (OpenAI):**
```python
except Exception as e:
    if "quota" in error_str or "429" in error_str or "rate_limit" in error_str:
        raise OCRException("Límite de OpenAI alcanzado...")
    if "invalid" in error_str or "400" in error_str or "413" in error_str:
        raise OCRInvalidImage("OpenAI no pudo procesar...")
```

---

## 🚀 Flujo de OCR (antes y después)

```
┌─────────────────────────────────────────────────────────┐
│  Usuario sube imagen de apuntes                         │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  Validación: tamaño, formato MIME, integridad         │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
    ┌─────────────────────────────┐
    │  GEMINI (ANTES)             │
    │  ✅ google-generativeai     │
    │  ✅ gemini-2.0-flash        │
    │  ✅ Rápido, Gratuito        │
    └─────────────────────────────┘
                 │
                 ▼
    ┌─────────────────────────────┐
    │  OPENAI (AHORA)             │
    │  ✅ openai client            │
    │  ✅ gpt-4o                  │
    │  ✅ Más preciso, Pago       │
    └─────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  Prompt optimizado para caligrafía manuscrita          │
│  (se mantiene igual)                                   │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  IA extrae texto, limpia markdown, valida [ILEGIBLE]  │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  Devuelve texto extraído al cliente                    │
│  (JSON: { "text": "..." })                             │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  Usuario usa el texto para:                            │
│  • Crear resumen                                       │
│  • Generar flashcards                                  │
│  • Chat con tutor                                      │
└─────────────────────────────────────────────────────────┘
```

---

## ⚙️ Configuración nuevas requeridas

### Variables de entorno (.env)

```env
# NUEVA: OpenAI para OCR
OPENAI_API_KEY=sk-proj-...

# OPCIONAL: Personalizar modelo
OPENAI_OCR_MODEL=gpt-4o          # Por defecto: gpt-4o
                                  # Alternativas: gpt-4-turbo, gpt-4

# EXISTENTES (se mantienen igual):
GROQ_API_KEY=...                 # Para resúmenes
DEEPSEEK_API_KEY=...             # Para flashcards
SECRET_KEY=...
```

### Obtener OpenAI API Key

1. Ir a: https://platform.openai.com/api/keys
2. Crear nueva Secret Key
3. Copiar el valor (aparece una sola vez)
4. Añadir a tu `.env`

---

## 📦 Cambios en dependencias

### requirements.txt

**Antes:**
```
google-generativeai>=0.8.0
groq==0.4.2
httpx==0.26.0
```

**Ahora:**
```
openai>=1.3.0           # NUEVO
groq==0.4.2             # Se mantiene
httpx==0.26.0           # Se mantiene
```

**Instalar:**
```bash
pip install openai>=1.3.0
# O simplemente:
pip install -r requirements.txt
```

---

## 🔧 API Endpoint (sin cambios externos)

El endpoint sigue siendo el mismo:

```http
POST /api/ocr-image
Content-Type: multipart/form-data

image: [archivo.jpg|.png|.webp|.gif]
```

**Respuesta:**
```json
{
  "text": "Texto extraído de la imagen..."
}
```

**Errores:**
```json
{
  "error": "Descripción del error"
}
```

---

## 📋 Manejo de excepciones

Todas las clases de excepción **se mantienen igual**:

```python
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
```

---

## 🎯 Prompt optimizado (se mantiene igual)

```python
OCR_PROMPT = """Eres un experto en transcripción de apuntes manuscritos.
Extrae TODO el texto visible en la imagen, respetando:
- Orden de lectura natural (izquierda a derecha, arriba a abajo).
- Saltos de línea y párrafos cuando sea evidente.
- No inventes contenido que no veas; si algo es ilegible, indica [ilegible] o omítelo.
- Mantén números, fórmulas y listas cuando sean claros.
- Devuelve ÚNICAMENTE el texto extraído, sin comentarios ni explicaciones.
- Si la imagen está borrosa, vacía o no contiene texto manuscrito, responde exactamente: [IMAGEN_ILEGIBLE]."""
```

---

## 💡 Ventajas de OpenAI Vision

### ✅ Ventajas
- **Precisión superior**: Mejor en caligrafía manuscrita variada
- **Multilingüe**: Detecta automáticamente idioma
- **Contexto**: Entiende mejor el contexto de los apuntes
- **Fórmulas**: Mejor reconocimiento de fórmulas matemáticas
- **Tablas**: Mejor estructura en tablas y diagramas

### ⚠️ Desventajas
- **Costo**: Pago por uso (es más caro que Gemini)
- **Límites**: Según tu plan de OpenAI
- **Cuota**: Hay límites de rate (no ilimitado como Gemini)

---

## 📊 Costos estimados

### OpenAI Vision (GPT-4o)
```
Imagen: $0.00765 USD por 1K tokens de imagen
Respuesta: $0.03 USD por 1K tokens

Ejemplo:
- 1 imagen típica (2MB) ≈ 1,000-2,000 tokens imagen
- Costo aproximado: $0.01-0.02 USD por OCR
```

### Comparación
| Servicio | Costo | Límite |
|----------|-------|--------|
| Gemini 2.0 Flash | Gratis | 15 req/min (tier gratis) |
| OpenAI Vision (GPT-4o) | ~$0.01-0.02/OCR | 500 req/min (plan pro) |

---

## 🔍 Archivos modificados

### 1. **config.py**
- ✅ Agregado: `OPENAI_API_KEY`
- ✅ Agregado: `OPENAI_OCR_MODEL`
- ✅ Removido: `GEMINI_API_KEY` y `GEMINI_OCR_MODEL`
- ✅ Agregado método: `validate_openai_ocr()`

### 2. **services/gemini_ocr.py**
- ✅ Import: `google-generativeai` → `openai`
- ✅ Cliente: Gemini GenerativeModel → OpenAI cliente
- ✅ Formato imagen: `inline_data` → `data URI base64`
- ✅ Comentarios: Actualizar referencias

### 3. **routes.py**
- ✅ Validación: `GEMINI_API_KEY` → `OPENAI_API_KEY`
- ✅ Comentarios: "Gemini Vision" → "OpenAI Vision"

### 4. **requirements.txt**
- ✅ Removido: `google-generativeai>=0.8.0`
- ✅ Agregado: `openai>=1.3.0`

### 5. **services/__init__.py**
- ✅ Comentarios: Actualizar referencias a OpenAI Vision

---

## ✨ Funcionalidad: totalmente preservada

La interfaz pública del OCR **no cambió**. El resto de la aplicación funciona exactamente igual:

```python
# Cliente sigue usando así:
text = await ocr_image_async(image_bytes, mime_type)

# Las excepciones son las mismas
try:
    text = await ocr_image_async(...)
except OCRImageTooLarge:
    # Usuario sube imagen demasiado grande
except OCRInvalidImage:
    # Formato no soportado
except OCRLowQuality:
    # Imagen borrosa
```

---

## 🚀 Testing local

```python
# Verificar configuración
from app.config import settings
settings.validate_openai_ocr()  # Valida OPENAI_API_KEY

# Probar OCR
from app.services.gemini_ocr import ocr_image_async

image_path = "path/to/handwritten_notes.jpg"
with open(image_path, "rb") as f:
    image_bytes = f.read()

try:
    text = await ocr_image_async(image_bytes, "image/jpeg")
    print(f"✅ Texto extraído: {text[:100]}...")
except Exception as e:
    print(f"❌ Error: {e}")
```

---

## 📚 Referencias

- **OpenAI Vision API**: https://platform.openai.com/docs/guides/vision
- **Modelos GPT-4**: https://platform.openai.com/docs/models
- **Límites de rate**: https://platform.openai.com/account/rate-limits
- **Precios OpenAI**: https://openai.com/pricing

---

## ⚡ Resumen rápido

| Aspecto | Cambio |
|---------|--------|
| **Qué cambió** | Gemini 2.0 Flash → OpenAI Vision (GPT-4o) |
| **Por qué** | Mayor precisión, mejor caligrafía, integración más simple |
| **Interfaz pública** | ✅ No cambió - 100% compatible |
| **API Key** | GEMINI_API_KEY → OPENAI_API_KEY |
| **Librería** | google-generativeai → openai |
| **Coste** | Gratis (con límites) → ~$0.01-0.02 por OCR |
| **Velocidad** | Similar - ambas rápidas |
| **Calidad** | Muy buena → Excelente |

**Conclusión**: Cambio de proveedor transparente, misma funcionalidad, mejor calidad resultado.
