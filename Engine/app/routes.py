import logging
import json
from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator, EmailStr
from slowapi import Limiter
from slowapi.util import get_remote_address
from typing import Optional, List, Dict, Annotated
import PyPDF2
import io

from app.config import settings
from app.services.ai_orchestrator import process_document_pipeline, chat_with_document

logger = logging.getLogger(__name__)

try:
    from app.services.openai_ocr import (
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

from app.database import (
    get_user_by_username, get_user_by_email, create_user,
    save_chat_message, update_user_last_login
)
from app.auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
    revoke_refresh_token,
    is_refresh_token_revoked,
    get_token_from_request,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
limiter = Limiter(key_func=get_remote_address)

MODOS_VALIDOS = ["general", "estudiar", "corto", "profesional"]

# ← Cache simple en memoria — sin dependencias externas
document_cache = {}

OCR_ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


# ============================================================
# PÁGINAS
# ============================================================

@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/app", response_class=HTMLResponse)
async def app_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})


@router.get("/privacy-policy", response_class=HTMLResponse)
async def privacy_policy_page(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})


@router.get("/terms-of-service", response_class=HTMLResponse)
async def terms_of_service(request: Request):
    return templates.TemplateResponse("terms-of-service.html", {"request": request})


@router.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    return templates.TemplateResponse("about.html", {"request": request})


@router.get("/contact", response_class=HTMLResponse)
async def contact(request: Request):
    return templates.TemplateResponse("contact.html", {"request": request})


# ============================================================
# MODELOS PYDANTIC
# ============================================================

class ResumenRequest(BaseModel):
    texto: str = Field(..., min_length=10, max_length=settings.MAX_TEXT_LENGTH)
    instrucciones: Optional[str] = ""
    modo: str = "general"
    task: str = "summary"

    @field_validator('modo')
    def validar_modo(cls, v):
        if v not in MODOS_VALIDOS:
            raise ValueError(f'Modo debe ser uno de: {", ".join(MODOS_VALIDOS)}')
        return v


class RegisterRequest(BaseModel):
    email: EmailStr
    username: Annotated[str, Field(..., min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_.-]+$")]
    password: Annotated[str, Field(..., min_length=8, max_length=128)]
    accept_privacy: bool = Field(default=False)

    @field_validator("accept_privacy")
    def must_accept_privacy(cls, v):
        if not v:
            raise ValueError("Debes aceptar la política de privacidad")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(..., min_length=8, max_length=128)]


# ============================================================
# OCR
# ============================================================

@router.post("/api/ocr-image")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def ocr_image_endpoint(request: Request, archivo: UploadFile = File(..., alias="image")):
    if not OCR_AVAILABLE:
        return JSONResponse(status_code=503, content={"error": "OCR no disponible."})
    if not archivo.filename:
        return JSONResponse(status_code=400, content={"error": "No se envió ningún archivo"})

    ext = (archivo.filename or "").lower().split(".")[-1]
    mime_map = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "webp": "image/webp", "gif": "image/gif"
    }
    mime_type = mime_map.get(ext) or (archivo.content_type or "").split(";")[0].strip().lower()
    if mime_type not in OCR_ALLOWED_MIMES:
        return JSONResponse(status_code=400, content={"error": "Formato no permitido."})

    try:
        contenido = await archivo.read()
    except (IOError, OSError, ValueError) as e:
        logger.exception("Error leyendo archivo OCR: %s", e)
        return JSONResponse(status_code=400, content={"error": "Error al leer la imagen"})
    except Exception as e:
        logger.exception("Error inesperado leyendo archivo OCR: %s", e)
        return JSONResponse(status_code=500, content={"error": "Error interno del servidor"})

    if len(contenido) > settings.OCR_MAX_IMAGE_SIZE:
        return JSONResponse(
            status_code=400,
            content={"error": f"Imagen demasiado grande. Máximo {settings.OCR_MAX_IMAGE_SIZE // (1024*1024)} MB."},
        )

    if not settings.OPENAI_API_KEY:
        return JSONResponse(status_code=503, content={"error": "OCR no disponible. Configura OPENAI_API_KEY."})

    try:
        text = await ocr_image_async(contenido, mime_type)
        return JSONResponse(content={"text": text})
    except OCRImageTooLarge as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except OCRInvalidImage as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except OCRLowQuality as e:
        return JSONResponse(status_code=422, content={"error": str(e)})
    except OCRBlockedOrEmpty as e:
        return JSONResponse(status_code=422, content={"error": str(e)})
    except OCRException as e:
        return JSONResponse(status_code=502, content={"error": str(e)})
    except Exception as e:
        logger.exception("OCR inesperado: %s", e)
        return JSONResponse(status_code=500, content={"error": "Error al procesar la imagen"})


# ============================================================
# RESUMIR — pipeline principal
# ============================================================

@router.post("/resumir", response_class=HTMLResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def resumir(
    request: Request,
    texto: str = Form(None),
    instrucciones: str = Form(""),
    modo: str = Form("general"),
    task: str = Form("summary"),
    archivo: UploadFile = File(None)
):
    processing_status = []

    try:
        if not texto and not (archivo and archivo.filename):
            return JSONResponse(status_code=400, content={"error": "Debes proporcionar texto o archivo"})

        if archivo and archivo.filename:
            contenido_bytes = await archivo.read()

            if archivo.filename.endswith(".txt"):
                try:
                    texto = contenido_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    texto = contenido_bytes.decode("latin-1")
                processing_status.append("📄 Archivo .txt cargado")

            elif archivo.filename.endswith(".pdf"):
                try:
                    pdf_file = io.BytesIO(contenido_bytes)
                    pdf_reader = PyPDF2.PdfReader(pdf_file)
                    texto = ""
                    for page in pdf_reader.pages:
                        texto += page.extract_text() + "\n"
                    processing_status.append(f"📄 PDF procesado: {len(pdf_reader.pages)} páginas")
                    if not texto.strip():
                        return JSONResponse(status_code=400, content={"error": "No se pudo extraer texto del PDF"})
                except Exception as e:
                    logger.error(f"Error procesando PDF: {e}")
                    return JSONResponse(status_code=500, content={"error": "Error al procesar el PDF"})

        if len(texto) > settings.MAX_TEXT_LENGTH:
            texto = texto[:settings.MAX_TEXT_LENGTH]

        datos = ResumenRequest(texto=texto, instrucciones=instrucciones, modo=modo, task=task)
        logger.info(f"Request desde {request.client.host} [modo: {datos.modo}, task: {datos.task}]")

        resultado, estructura, error_msg = await process_document_pipeline(
            text=datos.texto,
            modo=datos.modo,
            task=datos.task
        )

        if error_msg:
            return JSONResponse(status_code=500, content={"error": error_msg})

        session_id = None
        if estructura:
            session_id = str(hash(datos.texto[:100]))
            document_cache[session_id] = {
                "summary": resultado,
                "structure": estructura,
                "original_text": datos.texto[:5000]
            }
            logger.info(f"💾 Sesión guardada en caché: {session_id}")

        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or \
           request.headers.get("Accept", "").startswith("application/json"):
            return JSONResponse(content={
                "resumen": resultado if task not in ["flashcards", "mindmap"] else None,
                "flashcards": resultado if task == "flashcards" else None,
                "mindmap": resultado if task == "mindmap" else None,
                "estructura": estructura,
                "session_id": session_id,
                "modelo": "NXUS o.0.1"
            })

        return templates.TemplateResponse("index.html", {
            "request": request,
            "texto": datos.texto,
            "instrucciones": datos.instrucciones,
            "modo": modo,
            "resumen": resultado,
            "flashcards": resultado if task == "flashcards" else None,
            "estructura": estructura,
            "session_id": session_id,
            "error_msg": None,
            "processing_status": processing_status,
            "modelo": "NXUS o.0.1"
        })

    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        logger.error(f"Error inesperado: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


# ============================================================
# CHAT — Solo fuentes y General
# ============================================================

@router.post("/chat")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def chat_endpoint(request: Request):
    try:
        raw = await request.json()

        question = raw.get("question", "").strip()
        session_id = str(raw.get("session_id")) if raw.get("session_id") else None
        mode = raw.get("mode", "sources")
        history = raw.get("history", [])

        if not question:
            return JSONResponse(status_code=400, content={"error": "La pregunta no puede estar vacía"})

        logger.info(
            f"Chat | mode={mode} | session={session_id} | "
            f"cache_size={len(document_cache)} | "
            f"question={question[:50]}..."
        )

        doc_context = None
        if session_id:
            if session_id in document_cache:
                doc_context = document_cache[session_id]
                logger.info(f"✅ Contexto encontrado para sesión {session_id}")
            else:
                logger.warning(
                    f"⚠️ session_id '{session_id}' no encontrado. "
                    f"Cache tiene {len(document_cache)} entradas: {list(document_cache.keys())}"
                )

        if mode == "sources" and not doc_context:
            return JSONResponse(content={
                "answer": (
                    "⚠️ No encuentro el documento procesado en esta sesión. "
                    "Esto puede ocurrir si el servidor se reinició. "
                    "Por favor, vuelve a subir el documento para continuar."
                ),
                "mode": mode,
                "has_context": False
            })

        response_text = await chat_with_document(
            question=question,
            document_context=doc_context,
            mode=mode,
            history=history or []
        )

        return JSONResponse(content={
            "answer": response_text,
            "mode": mode,
            "has_context": doc_context is not None
        })

    except Exception as e:
        logger.error(f"Error en chat endpoint: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": f"Error procesando pregunta: {str(e)}"})


# ============================================================
# CHAT GENERAL CON STREAMING
# ============================================================

@router.post("/chat-general-stream")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def chat_general_stream(request: Request):
    try:
        data = await request.json()
        pregunta = data.get("pregunta", "")
        historial = data.get("historial", [])

        if not pregunta or not pregunta.strip():
            return JSONResponse(status_code=400, content={"error": "Pregunta vacía"})

        async def generate():
            from app.services.ai_orchestrator import ModelOrchestrator
            import httpx

            async with ModelOrchestrator() as orchestrator:
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "Eres StudIA, un asistente de estudio inteligente y amigable. "
                            "Ayudas a los estudiantes con cualquier pregunta académica. "
                            "Usa Markdown para formatear tus respuestas."
                        )
                    }
                ]

                for item in historial[-5:]:
                    messages.append({"role": "user", "content": item.get("pregunta", "")})
                    messages.append({"role": "assistant", "content": item.get("respuesta", "")})

                messages.append({"role": "user", "content": pregunta})

                try:
                    payload = {
                        "model": "deepseek-chat",
                        "messages": messages,
                        "max_tokens": 1024,
                        "temperature": 0.7,
                        "stream": True
                    }

                    async with httpx.AsyncClient(timeout=60.0) as client:
                        async with client.stream(
                            "POST",
                            "https://api.deepseek.com/v1/chat/completions",
                            headers={
                                "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                                "Content-Type": "application/json"
                            },
                            json=payload
                        ) as response:
                            async for line in response.aiter_lines():
                                if line.startswith("data: "):
                                    data_str = line[6:]
                                    if data_str == "[DONE]":
                                        yield "data: [DONE]\n\n"
                                        break
                                    try:
                                        chunk_data = json.loads(data_str)
                                        if chunk_data.get("choices"):
                                            delta = chunk_data["choices"][0].get("delta", {})
                                            content = delta.get("content", "")
                                            if content:
                                                yield f"data: {json.dumps({'content': content})}\n\n"
                                    except json.JSONDecodeError:
                                        continue

                except Exception as e:
                    logger.error(f"Error en streaming: {e}")
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )

    except Exception as e:
        logger.error(f"Error en chat-general-stream: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


# ============================================================
# AUTH
# ============================================================

@router.post("/register")
async def register(data: RegisterRequest):
    try:
        if get_user_by_email(data.email):
            return JSONResponse(status_code=400, content={"error": "Email ya registrado"})
        if get_user_by_username(data.username):
            return JSONResponse(status_code=400, content={"error": "Username ya existe"})

        hashed_password = get_password_hash(data.password)
        new_user = create_user(
            username=data.username,
            email=data.email,
            hashed_password=hashed_password
        )

        if not new_user:
            return JSONResponse(status_code=500, content={"error": "Error al crear usuario"})

        access_token = create_access_token({"user_id": new_user['id'], "email": new_user['email']})
        refresh_token = create_refresh_token({"user_id": new_user['id'], "email": new_user['email']})

        return JSONResponse(content={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": new_user['id'],
                "email": new_user['email'],
                "username": new_user['username']
            }
        })
    except Exception as e:
        logger.error(f"Error en registro: {e}")
        return JSONResponse(status_code=500, content={"error": "Error al crear usuario"})


@router.post("/login")
async def login(data: LoginRequest):
    try:
        user = get_user_by_email(data.email)
        if not user or not verify_password(data.password, user['hashed_password']):
            return JSONResponse(status_code=401, content={"error": "Email o contraseña incorrectos"})

        # Actualizar último login
        update_user_last_login(user['id'])

        access_token = create_access_token({"user_id": user['id'], "email": user['email']})
        refresh_token = create_refresh_token({"user_id": user['id'], "email": user['email']})

        return JSONResponse(content={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": user['id'],
                "email": user['email'],
                "username": user['username']
            }
        })
    except Exception as e:
        logger.error(f"Error en login: {e}")
        return JSONResponse(status_code=500, content={"error": "Error al iniciar sesión"})


@router.post("/token/refresh")
async def refresh_token_endpoint(request: Request):
    try:
        body = await request.json()
        refresh_token = body.get("refresh_token")
        if not refresh_token:
            return JSONResponse(status_code=400, content={"error": "refresh_token es requerido"})

        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            return JSONResponse(status_code=401, content={"error": "Refresh token inválido"})

        jti = payload.get("jti")
        if not jti or is_refresh_token_revoked(jti):
            return JSONResponse(status_code=401, content={"error": "Refresh token revocado"})

        access_token = create_access_token({
            "user_id": payload.get("user_id"),
            "email": payload.get("email")
        })
        return JSONResponse(content={"access_token": access_token, "token_type": "bearer"})

    except Exception as e:
        logger.exception("Error refresh token: %s", e)
        return JSONResponse(status_code=500, content={"error": "Error al refrescar token"})


@router.post("/logout")
async def logout(request: Request):
    try:
        body = await request.json()
        refresh_token = body.get("refresh_token")
        if not refresh_token:
            return JSONResponse(status_code=400, content={"error": "refresh_token es requerido"})

        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            return JSONResponse(status_code=401, content={"error": "Refresh token inválido"})

        jti = payload.get("jti")
        if not jti:
            return JSONResponse(status_code=400, content={"error": "Token inválido"})

        revoke_refresh_token(jti)
        return JSONResponse(content={"success": True})

    except Exception as e:
        logger.exception("Error en logout: %s", e)
        return JSONResponse(status_code=500, content={"error": "Error al hacer logout"})


# ============================================================
# SAVE CHAT
# ============================================================

@router.post("/save-chat")
async def save_chat(request: Request):
    try:
        data = await request.json()
        message = data.get("message")
        response = data.get("response")

        token = get_token_from_request(request)
        if not token:
            return JSONResponse(status_code=401, content={"error": "Token no proporcionado"})

        payload = decode_token(token)
        if not payload:
            return JSONResponse(status_code=401, content={"error": "Token inválido o expirado"})

        user = get_user_by_email(payload.get("email"))
        if not user:
            return JSONResponse(status_code=401, content={"error": "Usuario no encontrado"})

        save_chat_message(username=user['username'], message=message, response=response)
        return JSONResponse(content={"success": True})

    except Exception as e:
        logger.error(f"Error guardando chat: {e}")
        return JSONResponse(status_code=500, content={"error": "Error al guardar"})