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

# Logger (definir antes de usar en try/except)
logger = logging.getLogger(__name__)

# Import condicional de OCR (solo si está disponible)
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

# IMPORTS SIMPLIFICADOS (sin SQLAlchemy)
from app.database import get_user_by_username, get_user_by_email, create_user, save_chat_message
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

# Router
router = APIRouter()

# Configuración de templates
templates = Jinja2Templates(directory="app/templates")

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Modos disponibles
MODOS_VALIDOS = ["general", "estudiar", "corto", "profesional"]

# Cache temporal para estructura de documentos (en producción usar Redis)
document_cache = {}

# MIME types permitidos para OCR
OCR_ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    """Landing page principal"""
    return templates.TemplateResponse("landing.html", {"request": request})


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Página de login/registro"""
    return templates.TemplateResponse("login.html", {"request": request})


class ResumenRequest(BaseModel):
    """Modelo de validación para el request de resumen"""
    texto: str = Field(..., min_length=10, max_length=settings.MAX_TEXT_LENGTH)
    instrucciones: Optional[str] = ""
    modo: str = "general"
    task: str = "summary"

    @field_validator('modo')
    def validar_modo(cls, v):
        if v not in MODOS_VALIDOS:
            raise ValueError(f'Modo debe ser uno de: {", ".join(MODOS_VALIDOS)}')
        return v


@router.get("/app", response_class=HTMLResponse)
async def app_page(request: Request):
    """Página principal de la aplicación"""
    return templates.TemplateResponse("index.html", {"request": request})


@router.post("/api/ocr-image")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def ocr_image_endpoint(request: Request, archivo: UploadFile = File(..., alias="image")):
    """
    OCR de apuntes manuscritos con OpenAI Vision.
    Acepta multipart/form-data con campo 'image'. Devuelve el texto extraído.
    """
    if not OCR_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={"error": "OCR no disponible. El módulo de OCR no está disponible."},
        )

    if not archivo.filename:
        return JSONResponse(status_code=400, content={"error": "No se envió ningún archivo"})

    ext = (archivo.filename or "").lower().split(".")[-1]
    mime_map = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "webp": "image/webp", "gif": "image/gif"
    }
    mime_type = mime_map.get(ext) or (archivo.content_type or "").split(";")[0].strip().lower()
    if mime_type not in OCR_ALLOWED_MIMES:
        return JSONResponse(
            status_code=400,
            content={"error": "Formato no permitido. Usa JPG, PNG, WebP o GIF."},
        )

    try:
        contenido = await archivo.read()
    except Exception as e:
        logger.exception("Error leyendo archivo OCR: %s", e)
        return JSONResponse(status_code=400, content={"error": "Error al leer la imagen"})

    if len(contenido) > settings.OCR_MAX_IMAGE_SIZE:
        return JSONResponse(
            status_code=400,
            content={
                "error": f"Imagen demasiado grande. Máximo {settings.OCR_MAX_IMAGE_SIZE // (1024*1024)} MB."
            },
        )

    if not settings.OPENAI_API_KEY:
        return JSONResponse(
            status_code=503,
            content={"error": "OCR no disponible. Configura OPENAI_API_KEY en el servidor."},
        )

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
    """
    Endpoint principal con pipeline multi-modelo
    """
    processing_status = []

    try:
        if not texto and not (archivo and archivo.filename):
            return JSONResponse(
                status_code=400,
                content={"error": "Debes proporcionar texto o archivo"}
            )

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
                        return templates.TemplateResponse("index.html", {
                            "request": request,
                            "texto": "",
                            "error_msg": "No se pudo extraer texto del PDF",
                            "processing_status": processing_status
                        })

                except Exception as e:
                    logger.error(f"Error procesando PDF: {e}")
                    return templates.TemplateResponse("index.html", {
                        "request": request,
                        "error_msg": "Error al procesar el PDF",
                        "processing_status": processing_status
                    })

        if len(texto) > settings.MAX_TEXT_LENGTH:
            texto = texto[:settings.MAX_TEXT_LENGTH]
            processing_status.append(f"⚠️ Texto truncado a {settings.MAX_TEXT_LENGTH} caracteres")

        datos = ResumenRequest(
            texto=texto,
            instrucciones=instrucciones,
            modo=modo,
            task=task
        )

        logger.info(f"Request desde {request.client.host} [modo: {datos.modo}, task: {datos.task}]")

        processing_status.append("🔍 Analizando estructura...")

        resultado, estructura, error_msg = await process_document_pipeline(
            text=datos.texto,
            modo=datos.modo,
            task=datos.task
        )

        if error_msg:
            return templates.TemplateResponse("index.html", {
                "request": request,
                "texto": datos.texto,
                "error_msg": error_msg,
                "processing_status": processing_status
            })

        session_id = None
        if estructura:
            session_id = str(hash(datos.texto[:100]))
            document_cache[session_id] = {
                "summary": resultado,
                "structure": estructura,
                "original_text": datos.texto[:5000]
            }
            processing_status.append(f"✅ Documento procesado: {estructura.get('tema_principal', 'N/A')}")
            logger.info(f"💾 Sesión guardada en caché: {session_id}")

        template_data = {
            "request": request,
            "texto": datos.texto,
            "instrucciones": datos.instrucciones,
            "modo": modo,
            "resumen": resultado,
            "flashcards": resultado if datos.task == "flashcards" else None,
            "estructura": estructura,
            "session_id": session_id if estructura else None,
            "error_msg": None,
            "processing_status": processing_status,
            "modelo": "NXUS o.0.1"
        }

        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or \
           request.headers.get("Accept", "").startswith("application/json"):
            return JSONResponse(content={
                "resumen": resultado if datos.task not in ["flashcards", "mindmap"] else None,
                "flashcards": resultado if datos.task == "flashcards" else None,
                "mindmap": resultado if datos.task == "mindmap" else None,
                "estructura": estructura,
                "session_id": session_id if estructura else None,
                "modelo": "NXUS o.0.1"
            })

        return templates.TemplateResponse("index.html", template_data)

    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        return templates.TemplateResponse("index.html", {
            "request": request,
            "texto": texto,
            "error_msg": f"Error de validación: {str(e)}",
            "processing_status": processing_status
        })

    except Exception as e:
        logger.error(f"Error inesperado: {e}", exc_info=True)
        return templates.TemplateResponse("index.html", {
            "request": request,
            "texto": texto if 'texto' in locals() else "",
            "error_msg": f"Error del servidor: {str(e)}",
            "processing_status": processing_status
        })


# ============================================================
# CHAT — SOLO FUENTES Y GENERAL
# ============================================================

class ChatRequest(BaseModel):
    """Modelo para peticiones de chat"""
    question: str
    session_id: Optional[str] = None
    mode: str = "sources"
    history: Optional[List[Dict]] = []

    @field_validator('session_id', mode='before')
    @classmethod
    def coerce_session_id(cls, v):
        """Convierte session_id a string sea lo que sea (int, float, etc)"""
        if v is None:
            return None
        return str(v)


@router.post("/chat")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def chat_endpoint(request: Request, data: ChatRequest):
    """
    Endpoint de chat — modo 'sources' (con contexto de documento) y 'general'
    """
    try:
        logger.info(
            f"Chat request | Mode: {data.mode} | "
            f"Session: {data.session_id} | "
            f"Question: {data.question[:60]}..."
        )

        # Recuperar contexto del documento si existe en caché
        doc_context = None
        if data.session_id and data.session_id in document_cache:
            doc_context = document_cache[data.session_id]
            logger.info(f"✅ Contexto encontrado para sesión {data.session_id}")
        else:
            if data.mode == "sources":
                logger.warning(
                    f"⚠️ Sesión '{data.session_id}' no encontrada en caché. "
                    "El usuario debe procesar documentos primero (Resumir/Analizar)."
                )

        # Llamar al orquestador — devuelve string directamente
        response_text = await chat_with_document(
            question=data.question,
            document_context=doc_context,
            mode=data.mode,
            history=data.history or []    # ← AÑADIDO: pasar historial
        )

        return JSONResponse(content={
            "answer": response_text,
            "mode": data.mode,
            "has_context": doc_context is not None   # ← AÑADIDO: info para el frontend
        })

    except Exception as e:
        logger.error(f"Error en chat endpoint: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": f"Error procesando pregunta: {str(e)}"}
        )


# ============================================================
# CHAT GENERAL CON STREAMING (Server-Sent Events)
# ============================================================

@router.post("/chat-general-stream")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def chat_general_stream(request: Request):
    """
    Chat general con streaming (Server-Sent Events)
    """
    try:
        data = await request.json()
        logger.info(f"📩 Chat-general-stream - Data keys: {list(data.keys())}")

        pregunta = data.get("pregunta", "")
        historial = data.get("historial", [])

        logger.info(f"📝 Pregunta: '{pregunta[:60]}' | Historial: {len(historial)} items")

        if not pregunta or not pregunta.strip():
            logger.warning(f"⚠️ Pregunta vacía! Keys recibidas: {list(data.keys())}")
            return JSONResponse(
                status_code=400,
                content={"error": "Pregunta vacía", "debug": list(data.keys())}
            )

        logger.info(f"✅ Iniciando streaming desde {request.client.host}")

        async def generate():
            from app.services.ai_orchestrator import ModelOrchestrator
            import httpx

            async with ModelOrchestrator() as orchestrator:
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "Eres StudIA, un asistente de estudio inteligente y amigable. "
                            "Ayudas a los estudiantes con cualquier pregunta académica o de "
                            "conocimiento general. Responde de forma clara, precisa y educativa. "
                            "Usa Markdown para formatear tus respuestas (negritas, listas, etc)."
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
                                    except Exception:
                                        pass

                except Exception as e:
                    logger.error(f"Error en streaming DeepSeek: {e}")
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )

    except Exception as e:
        logger.error(f"Error en chat streaming: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "Error al procesar la pregunta"}
        )


# ============================================================
# AUTH
# ============================================================

class RegisterRequest(BaseModel):
    """Modelo para registro de usuario con validaciones."""
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
    """Modelo para login de usuario con validaciones."""
    email: EmailStr
    password: Annotated[str, Field(..., min_length=8, max_length=128)]


@router.post("/register")
async def register(data: RegisterRequest):
    """Registrar nuevo usuario"""
    try:
        existing_user = get_user_by_email(data.email)
        if existing_user:
            return JSONResponse(
                status_code=400,
                content={"error": "Email ya registrado"}
            )

        existing_username = get_user_by_username(data.username)
        if existing_username:
            return JSONResponse(
                status_code=400,
                content={"error": "Username ya existe"}
            )

        if not data.accept_privacy:
            return JSONResponse(
                status_code=400,
                content={"error": "Debes aceptar la política de privacidad"}
            )

        hashed_password = get_password_hash(data.password)
        new_user = create_user(
            username=data.username,
            email=data.email,
            hashed_password=hashed_password
        )

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
        return JSONResponse(
            status_code=500,
            content={"error": "Error al crear usuario"}
        )


@router.post("/login")
async def login(data: LoginRequest):
    """Login de usuario"""
    try:
        user = get_user_by_email(data.email)

        if not user or not verify_password(data.password, user['hashed_password']):
            return JSONResponse(
                status_code=401,
                content={"error": "Email o contraseña incorrectos"}
            )

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
        return JSONResponse(
            status_code=500,
            content={"error": "Error al iniciar sesión"}
        )


@router.post("/token/refresh")
async def refresh_token_endpoint(request: Request):
    """Genera un nuevo access token a partir de un refresh token"""
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

        access_token = create_access_token({"user_id": payload.get("user_id"), "email": payload.get("email")})
        return JSONResponse(content={"access_token": access_token, "token_type": "bearer"})

    except Exception as e:
        logger.exception("Error refresh token: %s", e)
        return JSONResponse(status_code=500, content={"error": "Error al refrescar token"})


@router.post("/logout")
async def logout(request: Request):
    """Revoca un refresh token (logout)"""
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
# PÁGINAS ESTÁTICAS
# ============================================================

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
# SAVE CHAT
# ============================================================

@router.post("/save-chat")
async def save_chat(request: Request):
    """Guardar mensaje de chat en historial - Autenticado con Bearer token"""
    try:
        data = await request.json()
        message = data.get("message")
        response = data.get("response")

        token = get_token_from_request(request)

        if not token:
            return JSONResponse(
                status_code=401,
                content={"error": "Token no proporcionado en Authorization header"}
            )

        payload = decode_token(token)
        if not payload:
            return JSONResponse(
                status_code=401,
                content={"error": "Token inválido o expirado"}
            )

        user_email = payload.get("email")
        user = get_user_by_email(user_email)

        if not user:
            return JSONResponse(
                status_code=401,
                content={"error": "Usuario no encontrado"}
            )

        save_chat_message(
            username=user['username'],
            message=message,
            response=response
        )

        return JSONResponse(content={"success": True})

    except Exception as e:
        logger.error(f"Error guardando chat: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Error al guardar"}
        )
