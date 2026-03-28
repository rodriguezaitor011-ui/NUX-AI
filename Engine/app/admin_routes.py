"""
Panel de Administración - NUX AI
Compatible con sistema JWT actual — lee datos de la base de datos SQL
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request

from app.auth import decode_token
from app.config import settings
from app.database import (
    get_database_stats,
    get_all_users_paginated,
    get_activity_by_day,
    load_chat_history,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)

# Lista de emails admin: desde configuración o fallback
ADMIN_EMAILS = (
    [e.strip() for e in settings.ADMIN_EMAILS if e.strip()]
    if settings.ADMIN_EMAILS
    else [
        "rodriguezaitor011@gmail.com",
        "aitordev7@gmail.com",
    ]
)


def is_admin(email: str) -> bool:
    """Verifica si el usuario es admin."""
    return bool(email) and email.lower() in [e.lower() for e in ADMIN_EMAILS]


def verify_admin_from_token(authorization: Optional[str] = Header(None)):
    """Verifica que el token JWT sea de un admin."""
    if not authorization:
        raise HTTPException(status_code=401, detail="No autorizado - Token requerido")

    token = authorization.replace("Bearer ", "").strip()
    payload = decode_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")

    email = payload.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Token inválido")

    if not is_admin(email):
        raise HTTPException(status_code=403, detail="Acceso denegado - Solo administradores")

    return payload


@router.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    """Página principal del panel admin."""
    return templates.TemplateResponse("admin.html", {"request": request})


@router.get("/api/admin/verify")
async def verify_admin(authorization: Optional[str] = Header(None)):
    """Verifica si el usuario es admin."""
    try:
        user = verify_admin_from_token(authorization)
        return {
            "is_admin": True,
            "email": user.get("email"),
            "user_id": user.get("user_id"),
        }
    except HTTPException:
        raise


@router.get("/api/admin/stats")
async def get_admin_stats(authorization: Optional[str] = Header(None)):
    """Obtiene estadísticas generales desde la base de datos SQL."""
    try:
        verify_admin_from_token(authorization)

        db_stats = get_database_stats()

        return {
            "users": {
                "total": db_stats.get("user_count", 0),
                "today": 0,
                "week": db_stats.get("active_users_7d", 0),
            },
            "chats": {
                "total": db_stats.get("chat_count", 0),
                "today": db_stats.get("chats_last_24h", 0),
                "week": 0,
                "average_per_user": (
                    round(db_stats.get("chat_count", 0) / max(db_stats.get("user_count", 1), 1), 2)
                ),
            },
            "most_active_user": {"username": "N/A", "chat_count": 0},
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error en get_admin_stats")
        return JSONResponse(
            status_code=500,
            content={"error": f"Error del servidor: {str(e)}"},
        )


@router.get("/api/admin/users")
async def get_users_list(
    authorization: Optional[str] = Header(None),
    page: int = 1,
    limit: int = 20,
    search: Optional[str] = None,
):
    """Lista de usuarios con paginación (SQL)."""
    try:
        verify_admin_from_token(authorization)
        result = get_all_users_paginated(page=page, limit=limit, search=search)

        # Marcar admins en la respuesta
        for u in result.get("users", []):
            u["is_admin"] = is_admin(u.get("email", ""))

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error en get_users_list")
        return JSONResponse(
            status_code=500,
            content={"error": f"Error del servidor: {str(e)}"},
        )


@router.get("/api/admin/activity")
async def get_activity_log(
    authorization: Optional[str] = Header(None),
    days: int = 7,
):
    """Actividad por día (últimos N días) desde SQL."""
    try:
        verify_admin_from_token(authorization)
        activity = get_activity_by_day(days=days)
        return {"activity": activity}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error en get_activity_log")
        return JSONResponse(
            status_code=500,
            content={"error": f"Error del servidor: {str(e)}"},
        )


@router.get("/api/admin/recent-chats")
async def get_recent_chats(
    authorization: Optional[str] = Header(None),
    limit: int = 10,
):
    """Chats recientes desde SQL."""
    try:
        verify_admin_from_token(authorization)
        history = load_chat_history(limit=limit, offset=0)

        chats_data = []
        for i, chat in enumerate(history):
            msg = chat.get("message", "")
            resp = chat.get("response", "")
            chats_data.append({
                "id": chat.get("id", i),
                "username": chat.get("username", "Unknown"),
                "message": msg[:100] + "..." if len(msg) > 100 else msg,
                "response": resp[:100] + "..." if len(resp) > 100 else resp,
                "timestamp": chat.get("timestamp", datetime.now().isoformat()),
            })

        return {"chats": chats_data}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error en get_recent_chats")
        return JSONResponse(
            status_code=500,
            content={"error": f"Error del servidor: {str(e)}"},
        )


@router.delete("/api/admin/users/{user_id}")
async def delete_user(user_id: str, authorization: Optional[str] = Header(None)):
    """Eliminación de usuarios deshabilitada por seguridad."""
    try:
        verify_admin_from_token(authorization)
        return JSONResponse(
            status_code=403,
            content={"error": "Eliminación de usuarios deshabilitada por seguridad"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error en delete_user")
        return JSONResponse(
            status_code=500,
            content={"error": f"Error del servidor: {str(e)}"},
        )
