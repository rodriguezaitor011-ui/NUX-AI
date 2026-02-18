"""
Panel de Administración Simplificado - NUX IA
Sin dependencia de base de datos
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
import json
import os

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Lista de usuarios admin
ADMIN_EMAILS = [
    "rodriguezaitor011@gmail.com",  # Cambiar por tu email
    "admin@nuxia.com"
]

DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
HISTORY_FILE = os.path.join(DATA_DIR, "chat_history.json")

# Asegurar que existe el directorio
os.makedirs(DATA_DIR, exist_ok=True)

def load_json(filepath, default=None):
    """Carga datos desde JSON"""
    if default is None:
        default = []
    
    if not os.path.exists(filepath):
        return default
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return default

def save_json(filepath, data):
    """Guarda datos en JSON"""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except:
        return False

def is_admin(email: str) -> bool:
    """Verifica si el usuario es admin"""
    return email.lower() in [e.lower() for e in ADMIN_EMAILS]

def verify_admin_token(token: str):
    """Verifica que el token sea de un admin"""
    users = load_json(USERS_FILE, [])
    
    for user in users:
        if user.get('token') == token:
            if is_admin(user.get('email', '')):
                return user
            else:
                raise HTTPException(status_code=403, detail="No autorizado - Solo administradores")
    
    raise HTTPException(status_code=401, detail="Token inválido")


@router.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    """Página principal del panel admin"""
    return templates.TemplateResponse("admin.html", {"request": request})


@router.get("/api/admin/stats")
async def get_admin_stats(token: str):
    """Obtiene estadísticas generales"""
    try:
        admin = verify_admin_token(token)
        
        users = load_json(USERS_FILE, [])
        history = load_json(HISTORY_FILE, [])
        
        # Total usuarios
        total_users = len(users)
        
        # Usuarios última semana
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        users_week = len([u for u in users if u.get('created_at', '') >= week_ago])
        
        # Total chats
        total_chats = len(history)
        
        # Chats hoy
        today = datetime.now().date().isoformat()
        chats_today = len([h for h in history if h.get('timestamp', '').startswith(today)])
        
        # Chats semana
        chats_week = len([h for h in history if h.get('timestamp', '') >= week_ago])
        
        # Usuario más activo
        user_counts = {}
        for h in history:
            username = h.get('username', 'Unknown')
            user_counts[username] = user_counts.get(username, 0) + 1
        
        most_active = max(user_counts.items(), key=lambda x: x[1]) if user_counts else ("N/A", 0)
        
        # Promedio
        avg_messages = round(total_chats / total_users, 2) if total_users > 0 else 0
        
        return {
            "users": {
                "total": total_users,
                "today": 0,  # No tenemos este dato
                "week": users_week
            },
            "chats": {
                "total": total_chats,
                "today": chats_today,
                "week": chats_week,
                "average_per_user": avg_messages
            },
            "most_active_user": {
                "username": most_active[0],
                "chat_count": most_active[1]
            }
        }
        
    except HTTPException as e:
        raise e
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error: {str(e)}"}
        )


@router.get("/api/admin/users")
async def get_users_list(token: str, page: int = 1, limit: int = 20, search: str = None):
    """Lista de usuarios"""
    try:
        admin = verify_admin_token(token)
        
        users = load_json(USERS_FILE, [])
        history = load_json(HISTORY_FILE, [])
        
        # Filtro búsqueda
        if search:
            users = [u for u in users if search.lower() in u.get('username', '').lower() or search.lower() in u.get('email', '').lower()]
        
        # Total
        total = len(users)
        
        # Paginación
        start = (page - 1) * limit
        end = start + limit
        paginated_users = users[start:end]
        
        # Enriquecer con datos
        users_data = []
        for user in paginated_users:
            username = user.get('username', 'Unknown')
            
            # Contar mensajes
            chat_count = len([h for h in history if h.get('username') == username])
            
            # Última actividad
            user_history = [h for h in history if h.get('username') == username]
            last_activity = max([h.get('timestamp', '') for h in user_history]) if user_history else None
            
            users_data.append({
                "id": user.get('id', user.get('username')),
                "username": username,
                "email": user.get('email', 'N/A'),
                "created_at": user.get('created_at', datetime.now().isoformat()),
                "chat_count": chat_count,
                "last_activity": last_activity,
                "is_admin": is_admin(user.get('email', ''))
            })
        
        return {
            "users": users_data,
            "total": total,
            "page": page,
            "pages": (total + limit - 1) // limit if total > 0 else 1
        }
        
    except HTTPException as e:
        raise e
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error: {str(e)}"}
        )


@router.get("/api/admin/activity")
async def get_activity_log(token: str, days: int = 7):
    """Actividad por día"""
    try:
        admin = verify_admin_token(token)
        
        history = load_json(HISTORY_FILE, [])
        
        # Agrupar por día
        activity_by_day = {}
        for h in history:
            date = h.get('timestamp', '')[:10]  # YYYY-MM-DD
            activity_by_day[date] = activity_by_day.get(date, 0) + 1
        
        # Últimos N días
        all_days = []
        for i in range(days):
            date = (datetime.now() - timedelta(days=days-i-1)).date().isoformat()
            all_days.append({
                "date": date,
                "count": activity_by_day.get(date, 0)
            })
        
        return {"activity": all_days}
        
    except HTTPException as e:
        raise e
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error: {str(e)}"}
        )


@router.get("/api/admin/recent-chats")
async def get_recent_chats(token: str, limit: int = 10):
    """Chats recientes"""
    try:
        admin = verify_admin_token(token)
        
        history = load_json(HISTORY_FILE, [])
        
        # Ordenar por timestamp descendente
        history.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        recent = history[:limit]
        
        chats_data = [
            {
                "id": i,
                "username": chat.get('username', 'Unknown'),
                "message": chat.get('message', '')[:100] + "..." if len(chat.get('message', '')) > 100 else chat.get('message', ''),
                "response": chat.get('response', '')[:100] + "..." if len(chat.get('response', '')) > 100 else chat.get('response', ''),
                "timestamp": chat.get('timestamp', datetime.now().isoformat())
            }
            for i, chat in enumerate(recent)
        ]
        
        return {"chats": chats_data}
        
    except HTTPException as e:
        raise e
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error: {str(e)}"}
        )


@router.delete("/api/admin/users/{user_id}")
async def delete_user(user_id: str, token: str):
    """Elimina usuario (deshabilitado por seguridad)"""
    try:
        admin = verify_admin_token(token)
        
        # Por seguridad, no permitimos eliminar usuarios en esta versión
        return JSONResponse(
            status_code=403,
            content={"error": "Eliminación de usuarios deshabilitada por seguridad"}
        )
        
    except HTTPException as e:
        raise e
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error: {str(e)}"}
        )
