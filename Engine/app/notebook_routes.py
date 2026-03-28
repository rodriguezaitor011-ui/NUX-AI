import logging
from fastapi import APIRouter, Request, Form, UploadFile, File, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional, List, Dict
import io
import PyPDF2
import json
import random

from app.database import db_session, Notebook, NotebookDocument, ChatHistory, get_user_by_email
from app.auth import get_token_from_request, decode_token
from app.services.ai_orchestrator import process_document_pipeline, ModelOrchestrator

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def get_current_user_from_request(request: Request) -> Optional[Dict]:
    token = get_token_from_request(request)
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    user = get_user_by_email(payload.get("email"))
    return user

async def generate_title_and_emoji(text: str) -> tuple[str, str, str]:
    """Usa IA para generar título corto, emoji y color base."""
    async with ModelOrchestrator() as orchestrator:
        prompt = "Analiza el siguiente texto y genera un objeto JSON con 3 campos: 'title' (título corto de máximo 4 palabras), 'emoji' (un emoji representativo), y 'color' (elige SOLO UNA de estas opciones: 'blue', 'purple', 'pink', 'orange', 'green'). RESPONDE SOLO CON EL JSON VÁLIDO."
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text[:3000]}
        ]
        response = await orchestrator._call_groq(
            model=orchestrator.MODELS["structure_analyst"],
            messages=messages,
            max_tokens=200,
            temperature=0.7
        )
        try:
            # Limpiar posible markdown
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            data = json.loads(response.strip())
            color_result = data.get("color", "blue")
            if color_result not in ["blue", "purple", "pink", "orange", "green"]:
                color_result = "blue"
            return data.get("title", "Nuevo Cuaderno"), data.get("emoji", "📓"), color_result
        except Exception:
            colors = ["blue", "purple", "pink", "orange", "green"]
            return "Nuevo Cuaderno de Estudio", "📓", random.choice(colors)

@router.get("/notebooks", response_class=HTMLResponse)
async def notebooks_page(request: Request):
    """Página principal de Cuadernos"""
    return templates.TemplateResponse("notebooks.html", {"request": request})

@router.get("/api/notebooks")
async def list_notebooks(request: Request):
    """Lista todos los cuadernos del usuario en JSON"""
    user = get_current_user_from_request(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "No autorizado"})
    
    try:
        with db_session() as db:
            notebooks = db.query(Notebook).filter(Notebook.user_id == user['id']).order_by(Notebook.updated_at.desc()).all()
            return JSONResponse(content={"notebooks": [nb.to_dict() for nb in notebooks]})
    except Exception as e:
        logger.error(f"Error listing notebooks: {e}")
        return JSONResponse(status_code=500, content={"error": "Error interno del servidor"})

@router.post("/api/notebooks")
async def create_notebook(
    request: Request,
    texto: str = Form(None),
    archivo: UploadFile = File(None)
):
    """Crea un cuaderno nuevo con texto o archivo"""
    user = get_current_user_from_request(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "No autorizado"})
    
    if not texto and not (archivo and archivo.filename):
        return JSONResponse(status_code=400, content={"error": "Debes proporcionar texto o archivo"})

    content_text = texto or ""
    filename = None
    
    if archivo and archivo.filename:
        filename = archivo.filename
        contenido_bytes = await archivo.read()
        if archivo.filename.endswith(".txt"):
            try:
                content_text = contenido_bytes.decode("utf-8")
            except Exception:
                content_text = contenido_bytes.decode("latin-1")
        elif archivo.filename.endswith(".pdf"):
            try:
                pdf_file = io.BytesIO(contenido_bytes)
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                content_text = ""
                for page in pdf_reader.pages:
                    content_text += page.extract_text() + "\n"
                if not content_text.strip():
                    return JSONResponse(status_code=400, content={"error": "No se pudo extraer texto del PDF"})
            except Exception as e:
                logger.error(f"Error procesando PDF: {e}")
                return JSONResponse(status_code=500, content={"error": "Error al procesar el PDF"})

    # Generar título con IA
    title, emoji, color = await generate_title_and_emoji(content_text)
    
    try:
        with db_session() as db:
            new_notebook = Notebook(
                user_id=user['id'],
                title=title,
                emoji=emoji,
                color=color
            )
            db.add(new_notebook)
            db.flush()
            db.refresh(new_notebook)
            nb_id = new_notebook.id

            new_doc = NotebookDocument(
                notebook_id=nb_id,
                filename=filename,
                content=content_text,
                structure=json.dumps({"info": "Estructura pendiente de análisis general"})
            )
            db.add(new_doc)
            db.flush()
            
            return JSONResponse(content={"success": True, "notebook": new_notebook.to_dict()})
            
    except Exception as e:
        logger.error(f"Error creando notebook: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.get("/api/notebooks/{notebook_id}")
async def get_notebook(notebook_id: int, request: Request):
    """Obtiene datos de un cuaderno, su doc y chats"""
    user = get_current_user_from_request(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "No autorizado"})

    try:
        with db_session() as db:
            notebook = db.query(Notebook).filter(Notebook.id == notebook_id, Notebook.user_id == user['id']).first()
            if not notebook:
                return JSONResponse(status_code=404, content={"error": "Cuaderno no encontrado"})
            
            doc = db.query(NotebookDocument).filter(NotebookDocument.notebook_id == notebook_id).first()
            chats = db.query(ChatHistory).filter(ChatHistory.notebook_id == notebook_id).order_by(ChatHistory.timestamp.asc()).all()
            
            return JSONResponse(content={
                "notebook": notebook.to_dict(),
                "document": doc.to_dict() if doc else None,
                "chats": [c.to_dict() for c in chats]
            })
    except Exception as e:
        logger.error(f"Error obteniendo notebook: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.delete("/api/notebooks/{notebook_id}")
async def delete_notebook(notebook_id: int, request: Request):
    """Elimina el cuaderno y sus dependencias (CASCADE)"""
    user = get_current_user_from_request(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "No autorizado"})

    try:
        with db_session() as db:
            notebook = db.query(Notebook).filter(Notebook.id == notebook_id, Notebook.user_id == user['id']).first()
            if not notebook:
                return JSONResponse(status_code=404, content={"error": "Cuaderno no encontrado"})
            db.delete(notebook)
            db.commit()
            return JSONResponse(content={"success": True})
    except Exception as e:
        logger.error(f"Error eliminando notebook: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})
