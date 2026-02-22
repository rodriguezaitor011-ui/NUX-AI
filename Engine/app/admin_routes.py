"""
Panel de Administración - NUX AI
Compatible con sistema JWT actual
"""

import logging
import threading
import json
import os
import tempfile
import shutil
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.auth import decode_token
from app.config import settings

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)

# Lock para operaciones en archivos JSON (evita concurrencia)
DATA_LOCK = threading.RLock()

# Lista de emails admin: desde configuración o fallback
ADMIN_EMAILS = (
    [e.strip() for e in settings.ADMIN_EMAILS if e.strip()]
    if settings.ADMIN_EMAILS
    else [
        "rodriguezaitor011@gmail.com",
        "aitordev7@gmail.com",
    ]
)

DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
HISTORY_FILE = os.path.join(DATA_DIR, "chat_history.json")

os.makedirs(DATA_DIR, exist_ok=True)


def load_json(filepath: str, default=None):
    """Carga datos desde JSON con manejo de errores específico."""
    if default is None:
        default = []
    if not os.path.exists(filepath):
        return default
    try:
        with DATA_LOCK:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError, OSError) as e:
        logger.error("Error cargando %s: %s", filepath, e)
        return default


def save_json(filepath: str, data) -> bool:
    """Guarda datos en JSON con escritura atómica."""
    try:
        tmp = filepath + ".tmp"
        with DATA_LOCK:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            shutil.move(tmp, filepath)
        return True
    except (IOError, OSError, TypeError) as e:
        logger.error("Error guardando %s: %s", filepath, e)
        return False


def is_admin(email: str) -> bool:
    """Verifica si el usuario es admin."""
    return email and email.lower() in [e.lower() for e in ADMIN_EMAILS]


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
    except HTTPException as e:
        raise e


@router.get("/api/admin/stats")
async def get_admin_stats(authorization: Optional[str] = Header(None)):
    """Obtiene estadísticas generales."""
    try:
        verify_admin_from_token(authorization)

        users = load_json(USERS_FILE, [])
        history = load_json(HISTORY_FILE, [])

        total_users = len(users)
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        users_week = sum(1 for u in users if u.get("created_at", "") >= week_ago)

        total_chats = len(history)
        today = datetime.now().date().isoformat()
        chats_today = sum(1 for h in history if (h.get("timestamp") or "").startswith(today))
        chats_week = sum(1 for h in history if (h.get("timestamp") or "") >= week_ago)

        user_counts = {}
        for h in history:
            username = h.get("username", "Unknown")
            user_counts[username] = user_counts.get(username, 0) + 1
        most_active = max(user_counts.items(), key=lambda x: x[1]) if user_counts else ("N/A", 0)

        avg_messages = round(total_chats / total_users, 2) if total_users > 0 else 0

        return {
            "users": {"total": total_users, "today": 0, "week": users_week},
            "chats": {
                "total": total_chats,
                "today": chats_today,
                "week": chats_week,
                "average_per_user": avg_messages,
            },
            "most_active_user": {"username": most_active[0], "chat_count": most_active[1]},
        }
    except HTTPException as e:
        raise e
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
    """Lista de usuarios con paginación."""
    try:
        verify_admin_from_token(authorization)

        users = load_json(USERS_FILE, [])
        history = load_json(HISTORY_FILE, [])

        if search:
            search_lower = search.lower()
            users = [
                u
                for u in users
                if search_lower in (u.get("username") or "").lower()
                or search_lower in (u.get("email") or "").lower()
            ]

        total = len(users)
        start = (page - 1) * limit
        end = start + limit
        paginated_users = users[start:end]

        users_data = []
        for user in paginated_users:
            username = user.get("username", "Unknown")
            user_history = [h for h in history if h.get("username") == username]
            last_activity = (
                max((h.get("timestamp", "") for h in user_history), default=None)
                if user_history
                else None
            )
            users_data.append({
                "id": user.get("id", username),
                "username": username,
                "email": user.get("email", "N/A"),
                "created_at": user.get("created_at", datetime.now().isoformat()),
                "chat_count": sum(1 for h in history if h.get("username") == username),
                "last_activity": last_activity,
                "is_admin": is_admin(user.get("email", "")),
            })

        return {
            "users": users_data,
            "total": total,
            "page": page,
            "pages": max(1, (total + limit - 1) // limit),
        }
    except HTTPException as e:
        raise e
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
    """Actividad por día (últimos N días)."""
    try:
        verify_admin_from_token(authorization)

        history = load_json(HISTORY_FILE, [])
        activity_by_day = {}
        for h in history:
            ts = h.get("timestamp", "")
            if ts:
                date = ts[:10]
                activity_by_day[date] = activity_by_day.get(date, 0) + 1

        all_days = []
        for i in range(days):
            date = (datetime.now() - timedelta(days=days - i - 1)).date().isoformat()
            all_days.append({"date": date, "count": activity_by_day.get(date, 0)})

        return {"activity": all_days}
    except HTTPException as e:
        raise e
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
    """Chats recientes."""
    try:
        verify_admin_from_token(authorization)

        history = load_json(HISTORY_FILE, [])
        sorted_history = sorted(
            history,
            key=lambda x: x.get("timestamp", ""),
            reverse=True,
        )
        recent = sorted_history[:limit]

        chats_data = []
        for i, chat in enumerate(recent):
            msg = chat.get("message", "")
            resp = chat.get("response", "")
            chats_data.append({
                "id": i,
                "username": chat.get("username", "Unknown"),
                "message": msg[:100] + "..." if len(msg) > 100 else msg,
                "response": resp[:100] + "..." if len(resp) > 100 else resp,
                "timestamp": chat.get("timestamp", datetime.now().isoformat()),
            })

        return {"chats": chats_data}
    except HTTPException as e:
        raise e
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
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.exception("Error en delete_user")
        return JSONResponse(
            status_code=500,
            content={"error": f"Error del servidor: {str(e)}"},
        )
