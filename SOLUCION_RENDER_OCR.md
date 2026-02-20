# 🔧 Solución Error Render: ModuleNotFoundError gemini_ocr

## ❌ Error Original

```
ModuleNotFoundError: No module named 'app.services.gemini_ocr'
```

Render está ejecutando desde `/opt/render/project/src/Engine/app/main.py` y no encuentra el módulo.

## ✅ Solución Implementada

### 1. **Import Condicional en `routes.py`**

Se ha modificado `Engine/app/routes.py` para hacer el import condicional:

```python
# Logger (definir antes de usar en try/except)
logger = logging.getLogger(__name__)

# Import condicional de OCR (solo si está disponible)
try:
    from app.services.gemini_ocr import (
        ocr_image_async,
        OCRException,
        OCRImageTooLarge,
        OCRInvalidImage,
        OCRLowQuality,
        OCRBlockedOrEmpty,
    )
    OCR_AVAILABLE = True
except (ImportError, ModuleNotFoundError) as e:
    OCR_AVAILABLE = False
    logger.warning(f"OCR no disponible: {e}. El endpoint /api/ocr-image estará deshabilitado.")
```

### 2. **Endpoint con Verificación**

El endpoint `/api/ocr-image` ahora verifica si OCR está disponible:

```python
@router.post("/api/ocr-image")
async def ocr_image_endpoint(...):
    if not OCR_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={"error": "OCR no disponible. El módulo gemini_ocr no está disponible."},
        )
    # ... resto del código
```

## 🔍 Verificaciones Necesarias

### 1. **Verificar que el archivo existe en el repositorio**

Asegúrate de que `Engine/app/services/gemini_ocr.py` esté en Git:

```bash
git add Engine/app/services/gemini_ocr.py
git commit -m "Añadir servicio OCR Gemini"
git push
```

### 2. **Verificar .gitignore**

Asegúrate de que `.gitignore` NO excluya `*.py` en `app/services/`:

```bash
# Verificar que no hay reglas que excluyan gemini_ocr.py
cat .gitignore | grep -E "(services|\.py)"
```

### 3. **Estructura de Carpetas en Render**

Render debe tener esta estructura:

```
Engine/
├── app/
│   ├── services/
│   │   ├── __init__.py
│   │   └── gemini_ocr.py  ← Debe existir
│   ├── routes.py
│   └── main.py
└── requirements.txt
```

### 4. **Verificar que requirements.txt incluye google-generativeai**

```bash
grep google-generativeai Engine/requirements.txt
# Debe mostrar: google-generativeai>=0.8.0
```

## 🚀 Pasos para Resolver en Render

1. **Verificar que el archivo está en Git:**
   ```bash
   git ls-files Engine/app/services/gemini_ocr.py
   ```

2. **Si no está, añadirlo:**
   ```bash
   git add Engine/app/services/gemini_ocr.py
   git commit -m "Añadir gemini_ocr.py para Render"
   git push
   ```

3. **Verificar que Render está usando la carpeta correcta:**
   - En Render Dashboard → Settings → Build Command
   - Asegúrate de que el working directory sea `Engine/` o que el build command ejecute desde ahí

4. **Si Render usa `engine/` (minúscula) en lugar de `Engine/`:**
   - Copia el archivo también a `engine/app/services/gemini_ocr.py`
   - O ajusta la configuración de Render para usar `Engine/`

## 📝 Alternativa: Hacer OCR Opcional

Si el archivo sigue sin encontrarse, la app ahora funciona sin OCR:

- El import condicional evita el crash
- El endpoint devuelve 503 con mensaje claro
- El frontend puede manejar el error y ocultar el botón OCR si no está disponible

## ✅ Estado Actual

- ✅ Import condicional implementado
- ✅ Endpoint con verificación `OCR_AVAILABLE`
- ✅ Logger definido antes del try/except
- ✅ Sin crashes si el módulo no existe
- ⚠️ Verificar que `gemini_ocr.py` esté en Git y se suba a Render

---

**Última actualización**: 2026-02-20
