# ✅ CHECKLIST DE DESPLIEGUE EN RENDER

## Configuración Render - Variables de Entorno

Estas son las **12 variables críticas** que **DEBEN estar configuradas** en el dashboard de Render:

```
✅ GROQ_API_KEY=gsk-...
✅ DEEPSEEK_API_KEY=...
✅ OPENAI_API_KEY=sk-...
✅ SECRET_KEY=... (generado con secrets.token_urlsafe(32))
✅ ADMIN_EMAILS=tu-email@example.com
✅ CORS_ORIGINS=tu-dominio-en-render.onrender.com
✅ DATABASE_URL=postgresql://... (Render genera automáticamente)
✅ ENVIRONMENT=production
✅ DEBUG=False
✅ MAX_TEXT_LENGTH=500000
✅ RATE_LIMIT_PER_MINUTE=10
✅ OPENAI_OCR_MODEL=gpt-4o
```

## Archivos y Configuración

### ✅ Procfile
- **Ubicación**: `engine/Procfile`
- **Estado**: ✅ Correcto
- **Contenido**: `web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`

### ✅ runtime.txt
- **Ubicación**: `engine/runtime.txt`
- **Estado**: ✅ Correcto
- **Versión Python**: `3.11.9`

### ✅ requirements.txt
- **Ubicación**: `engine/requirements.txt`
- **Estado**: ✅ Completo con:
  - fastapi, uvicorn
  - groq, openai, httpx
  - passlib, python-jose (autenticación)
  - python-dotenv
  - PyPDF2
  - slowapi (rate limiting)
  - pytest (testing)
  - pydantic, email-validator

### ✅ .gitignore
- **Ubicación**: `engine/.gitignore`
- **Estado**: ✅ Configurado correctamente
- **Protege**: `.env`, `__pycache__`, `*.db`, `data/`, `database/`

### ✅ .env.example
- **Ubicación**: `engine/.env.example`
- **Estado**: ✅ Completo y actualizado
- **Propósito**: Referencia para desarrolladores

### ✅ app/main.py
- **Status**: ✅ Arranca correctamente
- **Lifespan**: ✅ Valida config al inicio
- **CORS**, Rate Limiting: ✅ Configurados

### ✅ app/config.py
- **Status**: ✅ Lee todas las variables de entorno
- **Validaciones**: ✅ SECRET_KEY, GROQ, DEEPSEEK, CORS en producción
- **Fallbacks**: ✅ Valores por defecto sensatos

### ✅ app/routes.py
- **Importa**: `get_token_from_request` ✅
- **Endpoints**: OCR, Auth, Chat ✅
- **Autenticación**: Bearer tokens en Authorization header ✅

### ✅ app/services/openai_ocr.py
- **Status**: ✅ OCR de apuntes con OpenAI Vision
- **Validacion**: ✅ MIME types, tamaño máximo

### ✅ Tests
- **test_auth.py**: ✅ Tests de tokens y revocación
- **test_database.py**: ✅ Tests de persistencia JSON
- **CI/CD**: ✅ `.github/workflows/ci.yml` configura pytest
- **Comando**: `cd engine && pytest -q`

## Problemas Potenciales en Render

### ⚠️ DATABASE_URL
**Render proporciona automáticamente** una URL PostgreSQL. 
**importante**: Asegúrate de que está en las variables de entorno de Render.

Formato esperado:
```
postgresql://user:password@host:5432/dbname
```

### ⚠️ CORS_ORIGINS
**En desarrollo**: `CORS_ORIGINS=*`
**En Render (Producción)**: Debe ser tu dominio específico
```
CORS_ORIGINS=tu-app.onrender.com,www.tu-app.onrender.com
```

### ⚠️ Static Files
- **CSS**: `app/static/css/` ✅
- **JavaScript**: `app/static/js/` ✅
- **Fonts**: `app/static/fonts/` ✅
- **Translations**: `app/static/translations/` ✅

Render sirve archivos estáticos automáticamente desde la carpeta `static/`.

### ⚠️ Templates
- **Ubicación**: `app/templates/`
- **Archivos**: index.html, login.html, admin.html, etc. ✅

## Tests de Connectivity

### Verificar que todo funciona localmente:
```bash
cd engine

# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Crear archivo .env con tus valores
cp .env.example .env
nano .env  # Editar con tus API keys

# 3. Ejecutar tests
pytest -q

# 4. Ejecutar app
python run.py
# o
uvicorn app.main:app --reload
```

### Verificar en Render:
```bash
# Ver logs en tiempo real
# En dashboard Render → Logs

# Comprobar health check
curl https://tu-app.onrender.com/health
# Debería devolver: {"status": "healthy", "app": "NUX IA", "version": "2.0.0"}
```

## Proceso de Despliegue

1. **Push a GitHub**:
   ```bash
   git add -A
   git commit -m "Mejoras: tokens, OCR, tests"
   git push origin main
   ```

2. **En Render Dashboard**:
   - Conectar repositorio GitHub
   - Configure variables de entorno (las 12 mencionadas arriba)
   - Seleccionar rama `main`
   - Procfile automático
   - Runtime 3.11.9

3. **Render desplegará automáticamente** haciendo:
   ```bash
   pip install -r engine/requirements.txt
   APP_PORT=PORT uvicorn app.main:app --host 0.0.0.0
   ```

## Comandos Útiles para Debugging en Render

```bash
# Ver logs completos
# -> Dashboard → Logs (en tiempo real)

# SSH a instancia Render
# -> Services → (Tu app) → Shell

# Ver que puertos están abiertos
netstat -an | grep LISTEN

# Verificar variables de entorno
env | grep -E "GROQ|DEEPSEEK|OPENAI|SECRET"

# Probar conexión a API
curl https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"
```

## Checklist Final

- [ ] Las 12 variables **CRÍTICAS** están en Render
- [ ] `ENVIRONMENT=production` en Render
- [ ] `DEBUG=False` en Render
- [ ] `CORS_ORIGINS` apunta a tu dominio de Render (no `*`)
- [ ] BASE_URL en Render es correcto
- [ ] Tests pasan: `pytest -q`
- [ ] `.env` .gitignore: nunca commiteado a Git
- [ ] `Procfile` apunta a `app.main:app` ✅
- [ ] `requirements.txt` tiene todos los paquetes ✅
- [ ] `runtime.txt` tiene Python 3.11.9 ✅
- [ ] CI/CD workflow en `.github/workflows/ci.yml` pasa ✅

## Si algo falla en Render

1. **Revisa los logs**: Dashboard → Logs (últimas líneas de error)
2. **Verifica variables**: Dashboard → Environment → revisa todas las 12
3. **Tests locales**: `cd engine && pytest -q`
4. **Reinicia la instancia**: Dashboard → Services → Manual Deploy
5. **Revisa el Procfile**: Debe ser exacto: `web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`

---

**Fecha**: 2026-02-23  
**Versión**: NUX IA 2.2.0  
**Status**: ✅ Listo para Render
