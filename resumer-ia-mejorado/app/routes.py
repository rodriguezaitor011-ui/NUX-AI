import logging
import json
from fastapi import APIRouter, Request, Form, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address
from typing import Optional, List, Dict
import PyPDF2
import io
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.database import get_db, User, ChatHistory
from app.auth import verify_password, get_password_hash, create_access_token, decode_token

from app.config import settings
from app.services.ai_orchestrator import process_document_pipeline, chat_with_document

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
    texto: str = Field(..., min_length=10, description="Texto a resumir")
    instrucciones: str = Field(default="", max_length=200)
    modo: str = Field(default="general", description="Modo de resumen")
    task: str = Field(default="summary", description="Tarea: summary o flashcards")

    @field_validator('texto')
    @classmethod
    def texto_no_vacio(cls, v: str) -> str:
        if not v.strip():
            raise ValueError('El texto no puede estar vacío')
        return v

    @field_validator('modo')
    @classmethod
    def modo_valido(cls, v: str) -> str:
        if v not in MODOS_VALIDOS and v != "flashcards":
            return "general"
        return v


class ChatRequest(BaseModel):
    """Modelo de validación para el chat"""
    session_id: str = Field(..., description="ID de sesión")
    pregunta: str = Field(..., min_length=1)
    historial: List[Dict[str, str]] = Field(default=[])


@router.get("/app", response_class=HTMLResponse)
async def app_dashboard(request: Request):
    """Página principal"""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "texto": "",
            "instrucciones": "",
            "modo": "general",
            "resumen": None,
            "estructura": None,
            "error_msg": None,
            "processing_status": None
        }
    )


@router.post("/resumir", response_class=HTMLResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def resumir(
    request: Request,
    texto: str = Form(None),  # Ahora es opcional
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
            task=task  # ← Usar el parámetro task directamente
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
            session_id = str(hash(datos.texto[:100]))  # Simple hash para sesión
            document_cache[session_id] = {
                "summary": resultado,
                "structure": estructura,
                "original_text": datos.texto[:5000]  # Solo primeros 5k para referencia
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
            "texto": texto,
            "error_msg": "Error inesperado. Por favor intenta de nuevo.",
            "processing_status": processing_status
        })


@router.post("/chat")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def chat(request: Request, chat_data: ChatRequest):
    """
    Endpoint de chat con DeepSeek v3
    Usa el resumen comprimido como contexto
    """
    try:
        # Recuperar documento de caché
        doc_data = document_cache.get(chat_data.session_id)
        
        if not doc_data:
            return JSONResponse(
                status_code=404,
                content={"error": "Sesión no encontrada. Genera primero un resumen."}
            )
        
        logger.info(f"Chat request para sesión {chat_data.session_id}")
        
        # Llamar al tutor con contexto comprimido
        respuesta, error_msg = await chat_with_document(
            summary=doc_data["summary"],
            structure=doc_data["structure"],
            question=chat_data.pregunta,
            history=chat_data.historial
        )
        
        if error_msg:
            return JSONResponse(
                status_code=500,
                content={"error": error_msg}
            )
        
        return JSONResponse(content={
            "respuesta": respuesta,
            "modelo": "DeepSeek v3",
            "tema": doc_data["structure"].get("tema_principal", "N/A")
        })
        
    except Exception as e:
        logger.error(f"Error en chat: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "Error al procesar la pregunta"}
        )


@router.post("/chat-general-stream")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def chat_general_stream(request: Request):
    """
    Chat general con streaming (Server-Sent Events)
    """
    try:
        data = await request.json()
        pregunta = data.get("pregunta", "")
        historial = data.get("historial", [])
        
        if not pregunta:
            return JSONResponse(
                status_code=400,
                content={"error": "Pregunta vacía"}
            )
        
        logger.info(f"Chat general streaming desde {request.client.host}")
        
        async def generate():
            from app.services.ai_orchestrator import ModelOrchestrator
            import httpx
            
            async with ModelOrchestrator() as orchestrator:
                # Construir mensajes
                messages = [
                    {
                        "role": "system",
                        "content": "Eres StudIA, un asistente de estudio inteligente y amigable. Ayudas a los estudiantes con cualquier pregunta académica o de conocimiento general. Responde de forma clara, precisa y educativa. Usa Markdown para formatear tus respuestas (negritas, listas, etc)."
                    }
                ]
                
                # Historial
                for item in historial[-5:]:
                    messages.append({"role": "user", "content": item["pregunta"]})
                    messages.append({"role": "assistant", "content": item["respuesta"]})
                
                # Pregunta actual
                messages.append({"role": "user", "content": pregunta})
                
                # Llamar a DeepSeek con streaming
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
                                        import json
                                        chunk_data = json.loads(data_str)
                                        
                                        if chunk_data.get("choices"):
                                            delta = chunk_data["choices"][0].get("delta", {})
                                            content = delta.get("content", "")
                                            
                                            if content:
                                                yield f"data: {json.dumps({'content': content})}\n\n"
                                    except:
                                        pass
                        
                except Exception as e:
                    logger.error(f"Error en streaming: {e}")
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


@router.post("/chat-general")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def chat_general(request: Request):
    """
    Chat general sin restricciones de documentos
    DeepSeek v3 responde cualquier pregunta
    """
    try:
        data = await request.json()
        pregunta = data.get("pregunta", "")
        historial = data.get("historial", [])
        
        if not pregunta:
            return JSONResponse(
                status_code=400,
                content={"error": "Pregunta vacía"}
            )
        
        logger.info(f"Chat general request desde {request.client.host}")
        
        # Importar DeepSeek client
        from app.services.ai_orchestrator import ModelOrchestrator
        
        async with ModelOrchestrator() as orchestrator:
            # Construir mensajes sin contexto de documento
            messages = [
                {
                    "role": "system",
                    "content": "Eres StudIA, un asistente de estudio inteligente y amigable. Ayudas a los estudiantes con cualquier pregunta académica o de conocimiento general. Responde de forma clara, precisa y educativa."
                }
            ]
            
            # Añadir historial (últimas 5 interacciones)
            for item in historial[-5:]:
                messages.append({"role": "user", "content": item["pregunta"]})
                messages.append({"role": "assistant", "content": item["respuesta"]})
            
            # Pregunta actual
            messages.append({"role": "user", "content": pregunta})
            
            # Llamar a DeepSeek
            respuesta = await orchestrator._call_deepseek(
                messages=messages,
                max_tokens=1024,
                temperature=0.7
            )
            
            if not respuesta:
                return JSONResponse(
                    status_code=500,
                    content={"error": "Error al generar respuesta"}
                )
            
            return JSONResponse(content={
                "respuesta": respuesta,
                "modelo": "DeepSeek v3"
            })
        
    except Exception as e:
        logger.error(f"Error en chat general: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "Error al procesar la pregunta"}
        )


@router.get("/status/{session_id}")
async def get_session_status(session_id: str):
    """Endpoint para verificar estado de sesión"""
    doc_data = document_cache.get(session_id)
    
    if not doc_data:
        return JSONResponse(
            status_code=404,
            content={"exists": False}
        )
    
    return JSONResponse(content={
        "exists": True,
        "tema": doc_data["structure"].get("tema_principal", "N/A"),
        "conceptos": doc_data["structure"].get("conceptos_clave", [])[:5]
    })

# ========================================
# AUTH ENDPOINTS
# ========================================

class RegisterRequest(BaseModel):
    """Modelo para registro de usuario"""
    email: str = Field(..., min_length=5, max_length=255)
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    accept_privacy: bool = Field(default=False)

class LoginRequest(BaseModel):
    """Modelo para login de usuario"""
    email: str
    password: str

@router.post("/register")
async def register(data: RegisterRequest, db: Session = Depends(get_db)):
    """Registrar nuevo usuario"""
    try:
        # Verificar si el email ya existe
        existing_user = db.query(User).filter(User.email == data.email).first()
        if existing_user:
            return JSONResponse(
                status_code=400,
                content={"error": "Email ya registrado"}
            )
        
        # Verificar que aceptó la política
        if not data.accept_privacy:
            return JSONResponse(
                status_code=400,
                content={"error": "Debes aceptar la política de privacidad"}
            )
        
        # Crear usuario
        hashed_password = get_password_hash(data.password)
        new_user = User(
            email=data.email,
            username=data.username,
            hashed_password=hashed_password
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        # Crear token
        token = create_access_token({"user_id": new_user.id, "email": new_user.email})
        
        return JSONResponse(content={
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": new_user.id,
                "email": new_user.email,
                "username": new_user.username,
                "is_pro": new_user.is_pro
            }
        })
        
    except Exception as e:
        logger.error(f"Error en registro: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Error al crear usuario"}
        )

@router.post("/login")
async def login(data: LoginRequest, db: Session = Depends(get_db)):
    """Login de usuario"""
    try:
        # Buscar usuario
        user = db.query(User).filter(User.email == data.email).first()
        
        if not user or not verify_password(data.password, user.hashed_password):
            return JSONResponse(
                status_code=401,
                content={"error": "Email o contraseña incorrectos"}
            )
        
        # Crear token
        token = create_access_token({"user_id": user.id, "email": user.email})
        
        return JSONResponse(content={
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,  # ← AÑADIDO
                "is_pro": user.is_pro
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
async def save_chat(
    request: Request,
    db: Session = Depends(get_db)
):
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
        
        # Decodificar token para obtener user_id
        payload = decode_token(token)
        if not payload:
            return JSONResponse(
                status_code=401,
                content={"error": "Token inválido"}
            )
        
        user_id = payload.get("user_id")
        
        # Guardar en DB
        chat_entry = ChatHistory(
            user_id=user_id,
            message=message,
            response=response
        )
        db.add(chat_entry)
        db.commit()
        
        return JSONResponse(content={"success": True})
        
    except Exception as e:
        logger.error(f"Error guardando chat: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Error al guardar"}
        )