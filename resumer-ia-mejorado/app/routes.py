import logging
import json
from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address
from typing import Optional, List, Dict
import PyPDF2
import io

from app.config import settings
from app.services.ai_orchestrator import process_document_pipeline, chat_with_document

# IMPORTS SIMPLIFICADOS (sin SQLAlchemy)
from app.database import get_user_by_username, get_user_by_email, create_user, save_chat_message
from app.auth import verify_password, get_password_hash, create_access_token, decode_token

#Router
router = APIRouter()

# Configuración de templates
templates = Jinja2Templates(directory="app/templates")

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


# Modos disponibles
MODOS_VALIDOS = ["general", "estudiar", "corto", "profesional"]

# Cache temporal para estructura de documentos (en producción usar Redis)
document_cache = {}


@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    """Landing page principal"""
    return templates.TemplateResponse("landing.html", {"request": request})
    
logger = logging.getLogger(__name__)

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
        # Validar que al menos uno existe
        if not texto and not (archivo and archivo.filename):
            return JSONResponse(
                status_code=400,
                content={"error": "Debes proporcionar texto o archivo"}
            )
        
        # Procesar archivo si existe
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

        # Truncar si es muy largo
        if len(texto) > settings.MAX_TEXT_LENGTH:
            texto = texto[:settings.MAX_TEXT_LENGTH]
            processing_status.append(f"⚠️ Texto truncado a {settings.MAX_TEXT_LENGTH} caracteres")

        # Validar datos
        datos = ResumenRequest(
            texto=texto,
            instrucciones=instrucciones,
            modo=modo,
            task=task
        )
        

        logger.info(f"Request desde {request.client.host} [modo: {datos.modo}, task: {datos.task}]")
        
        # === PIPELINE MULTI-MODELO ===
        processing_status.append("🔍 Analizando estructura (Llama 4 Scout)...")
        
        # Ejecutar pipeline
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
        
        # Guardar estructura en caché para el chat
        if estructura:
            session_id = str(hash(datos.texto[:100]))
            document_cache[session_id] = {
                "summary": resultado,
                "structure": estructura,
                "original_text": datos.texto[:5000]
            }
            processing_status.append(f"✅ Documento procesado: {estructura.get('tema_principal', 'N/A')}")
        
        # Determinar qué mostrar
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
        
        # Si es una petición AJAX (desde JS), devolver JSON
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


class ChatRequest(BaseModel):
    """Modelo para peticiones de chat"""
    question: str
    session_id: Optional[str] = None
    mode: str = "sources"


@router.post("/chat")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def chat_endpoint(request: Request, data: ChatRequest):
    """
    Endpoint de chat mejorado
    """
    try:
        logger.info(f"Chat request - Mode: {data.mode}, Session: {data.session_id}")
        
        # Verificar si hay documento en caché
        doc_context = None
        if data.session_id and data.session_id in document_cache:
            doc_context = document_cache[data.session_id]
        
        # Llamar al chat
        response_text = await chat_with_document(
            question=data.question,
            document_context=doc_context,
            mode=data.mode
        )
        
        return JSONResponse(content={
            "answer": response_text,
            "mode": data.mode
        })
        
    except Exception as e:
        logger.error(f"Error en chat: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": f"Error procesando pregunta: {str(e)}"}
        )


# === AUTH ROUTES (SIMPLIFICADAS SIN SQLALCHEMY) ===

class RegisterRequest(BaseModel):
    """Modelo para registro de usuario"""
    email: str
    username: str
    password: str
    accept_privacy: bool = Field(default=False)

class LoginRequest(BaseModel):
    """Modelo para login de usuario"""
    email: str
    password: str

@router.post("/register")
async def register(data: RegisterRequest):
    """Registrar nuevo usuario"""
    try:
        # Verificar si el email ya existe
        existing_user = get_user_by_email(data.email)
        if existing_user:
            return JSONResponse(
                status_code=400,
                content={"error": "Email ya registrado"}
            )
        
        # Verificar username
        existing_username = get_user_by_username(data.username)
        if existing_username:
            return JSONResponse(
                status_code=400,
                content={"error": "Username ya existe"}
            )
        
        # Verificar que aceptó la política
        if not data.accept_privacy:
            return JSONResponse(
                status_code=400,
                content={"error": "Debes aceptar la política de privacidad"}
            )
        
        # Crear usuario
        hashed_password = get_password_hash(data.password)
        new_user = create_user(
            username=data.username,
            email=data.email,
            hashed_password=hashed_password
        )
        
        # Crear token
        token = create_access_token({"user_id": new_user['id'], "email": new_user['email']})
        
        return JSONResponse(content={
            "access_token": token,
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
        # Buscar usuario
        user = get_user_by_email(data.email)
        
        if not user or not verify_password(data.password, user['hashed_password']):
            return JSONResponse(
                status_code=401,
                content={"error": "Email o contraseña incorrectos"}
            )
        
        # Crear token
        token = create_access_token({"user_id": user['id'], "email": user['email']})
        
        return JSONResponse(content={
            "access_token": token,
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

@router.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    """Página de política de privacidad"""
    return templates.TemplateResponse("privacy.html", {"request": request})

@router.post("/save-chat")
async def save_chat(request: Request):
    """Guardar mensaje de chat en historial"""
    try:
        data = await request.json()
        token = data.get("token")
        message = data.get("message")
        response = data.get("response")
        
        if not token:
            return JSONResponse(
                status_code=401,
                content={"error": "No autenticado"}
            )
        
        # Decodificar token para obtener user info
        payload = decode_token(token)
        if not payload:
            return JSONResponse(
                status_code=401,
                content={"error": "Token inválido"}
            )
        
        # Obtener username del payload (necesitamos añadirlo al token)
        user_email = payload.get("email")
        user = get_user_by_email(user_email)
        
        if not user:
            return JSONResponse(
                status_code=401,
                content={"error": "Usuario no encontrado"}
            )
        
        # Guardar chat
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
