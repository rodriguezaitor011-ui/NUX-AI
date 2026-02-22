# Cambios realizados - Resumen técnico

Este documento resume los cambios realizados en el repo durante la auditoría y corrección rápida.

**Objetivo:** corregir errores críticos, mejorar seguridad/validación y añadir tests/CI básicos.

---

**Cambios principales (por archivo)**

- `engine/app/auth.py`
  - Reemplazado `datetime.utcnow()` por `datetime.now(timezone.utc)` para compatibilidad con Python 3.12+ y uso de datetimes con zona.
  - Ajustado `ACCESS_TOKEN_EXPIRE_MINUTES` a 2 horas.
  - Añadida generación de `refresh` tokens mediante `create_refresh_token()` con `jti` único.
  - Añadido almacenamiento atómico y revocación de refresh tokens en `data/revoked_refresh_tokens.json` (con lock de hilos).

- `engine/app/services/gemini_ocr.py` → renombrado y reemplazado por `engine/app/services/openai_ocr.py`
  - El servicio OCR ahora está claramente nombrado `openai_ocr.py` (el código ya usaba la librería `openai`).
  - Implementa `extract_text_from_image()` y `ocr_image_async()` con validaciones MIME/tamaño, limpieza de texto y manejo de errores específicos.

- `engine/app/routes.py`
  - Import actualizado a `app.services.openai_ocr` y manejo condicional si falta el módulo (endpoint OCR responde 503 si no disponible).
  - Añadidos modelos Pydantic `RegisterRequest` y `LoginRequest` con validaciones (`EmailStr`, `constr`, longitudes mín/máx, regex para username).
  - `register` y `login` ahora devuelven `access_token` y `refresh_token`.
  - Nuevos endpoints: `/token/refresh` (genera nuevo access token desde refresh token) y `/logout` (revoca refresh token).

- `engine/app/admin_routes.py`
  - Añadido `DATA_LOCK` (threading.RLock) para proteger lecturas/escrituras a archivos JSON usados por admin.
  - Corrección: reemplazado `json.JSONEncodeError` inválido por `TypeError` en excepciones de escritura.

- `engine/app/database.py`
  - Añadido `DATA_LOCK` (threading.RLock) y envuelto `load_*` y `save_*` para operaciones atómicas seguras.
  - Inicialización de archivos `users.json` y `chat_history.json` ahora usa locks.
  - Excepciones ajustadas para `save_*` a `TypeError` en lugar de `json.JSONEncodeError` inexistente.

- Tests y CI
  - Añadidos tests básicos en `engine/tests/`:
    - `test_auth.py`: crea/verifica access + refresh tokens y flujo de revocación (usa archivo temporal).
    - `test_database.py`: prueba guardado/carga de usuarios e historial usando rutas temporales.
  - Añadido `pytest` a `engine/requirements.txt`.
  - Añadido `engine/TESTING.md` con instrucciones rápidas para ejecutar tests localmente.
  - Añadido workflow GitHub Actions: `.github/workflows/ci.yml` para ejecutar `pytest` en push/PR.

---

**Decisiones de diseño y motivación**

- Locks para JSON: el proyecto usa archivos JSON como datasource; para evitar corrupción por concurrencia he añadido `threading.RLock` y escrituras atómicas con archivos temporales.
- Refresh tokens: implementar refresh tokens permite emitir access tokens de corta duración y revocarlos fácilmente mediante `jti` almacenado.
- Renombrado OCR: el archivo original se llamaba `gemini_ocr.py` pero el código y la configuración usan OpenAI; renombrar reduce confusión y riesgo de mantener código huérfano.
- Validación de entrada: Pydantic mejora seguridad y reduce errores por inputs malformados.

---

**Cómo probar rápidamente los cambios (local)**

1. Crear entorno virtual e instalar dependencias:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install --upgrade pip
pip install -r engine/requirements.txt
```

2. Ejecutar tests:

```bash
cd engine
pytest -q
```

Nota: en el entorno actual no se detectó `pytest` instalado globalmente, por eso añadimos `engine/requirements.txt` y un workflow CI.

---

**Siguientes recomendaciones (prioridad alta → baja)**

- Forzar validación `OPENAI_API_KEY` sólo cuando se use OCR (ya hay validación condicional, considerar `settings.validate_openai_ocr()` en rutas que usen OCR).
- Migrar de JSON a una base de datos ligera (SQLite/Postgres) para producción; archivos JSON no escalan.
- Implementar HTTPS, cabeceras de seguridad y CSRF protections para el frontend.
- Añadir refresh-token rotation y expiración en servidor (mejorar revocación y limitación de reuse).
- Añadir más tests (end-to-end para registro/login/refresh + endpoints OCR) y cobertura de CI.

---

Si quieres, actualizo `README.md` y creo un `.env.example` con las variables nuevas (`SECRET_KEY`, `OPENAI_API_KEY`, `OPENAI_OCR_MODEL`, `RATE_LIMIT_PER_MINUTE`, `CORS_ORIGINS`) y modifico `MEJORAS_IMPLEMENTADAS.md` para reflejar estos cambios. ¿Procedo con eso?
