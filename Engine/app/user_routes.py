"""
User profile and additional functionality routes.
"""

import logging
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from app.auth import get_token_from_request, decode_token
from app.database import (
    get_user_by_email, get_user_by_id, update_user_last_login,
    get_user_chat_history, get_recent_sessions, get_database_stats
)
from app.cache import get_cache, cached_function

logger = logging.getLogger(__name__)
router = APIRouter()


def get_current_user(request: Request) -> Optional[Dict]:
    """Get current user from JWT token"""
    token = get_token_from_request(request)
    if not token:
        return None
    
    payload = decode_token(token)
    if not payload:
        return None
    
    user = get_user_by_email(payload.get("email"))
    if user:
        # Update last login time
        update_user_last_login(user['id'])
    
    return user


@router.get("/api/user/profile")
async def get_user_profile(request: Request):
    """Get current user profile"""
    user = get_current_user(request)
    if not user:
        return JSONResponse(
            status_code=401,
            content={"error": "No autorizado"}
        )
    
    # Remove sensitive data
    user_profile = user.copy()
    user_profile.pop('hashed_password', None)
    
    return JSONResponse(content={
        "user": user_profile,
        "timestamp": datetime.now().isoformat()
    })


@router.get("/api/user/stats")
async def get_user_stats(request: Request):
    """Get user statistics"""
    user = get_current_user(request)
    if not user:
        return JSONResponse(
            status_code=401,
            content={"error": "No autorizado"}
        )
    
    # Get chat history stats
    chat_history = get_user_chat_history(user['username'], limit=1000)
    total_chats = len(chat_history)
    
    # Get recent sessions
    recent_sessions = get_recent_sessions(user['username'], days=7)
    
    # Calculate activity
    today = datetime.now().date()
    weekly_activity = {}
    for i in range(7):
        date = today - timedelta(days=i)
        date_str = date.isoformat()
        chats_on_date = len([c for c in chat_history 
                           if datetime.fromisoformat(c['timestamp']).date() == date])
        weekly_activity[date_str] = chats_on_date
    
    return JSONResponse(content={
        "stats": {
            "total_chats": total_chats,
            "recent_sessions": len(recent_sessions),
            "weekly_activity": weekly_activity,
            "last_login": user.get('last_login'),
            "account_age_days": (
                (datetime.now() - datetime.fromisoformat(user['created_at'])).days 
                if user.get('created_at') else 0
            )
        }
    })


@router.get("/api/user/chats")
async def get_user_chats(request: Request, limit: int = 50, offset: int = 0):
    """Get user chat history"""
    user = get_current_user(request)
    if not user:
        return JSONResponse(
            status_code=401,
            content={"error": "No autorizado"}
        )
    
    chats = get_user_chat_history(user['username'], limit=limit, offset=offset)
    
    return JSONResponse(content={
        "chats": chats,
        "total": len(chats),
        "limit": limit,
        "offset": offset
    })


@router.get("/api/user/sessions")
async def get_user_sessions(request: Request, days: int = 7):
    """Get user recent sessions"""
    user = get_current_user(request)
    if not user:
        return JSONResponse(
            status_code=401,
            content={"error": "No autorizado"}
        )
    
    sessions = get_recent_sessions(user['username'], days=days)
    
    return JSONResponse(content={
        "sessions": sessions,
        "days": days
    })


@router.get("/api/system/stats")
@cached_function(ttl=60, key_prefix="system_stats")  # Cache for 1 minute
async def get_system_stats():
    """Get system statistics (cached)"""
    try:
        db_stats = get_database_stats()
        
        # Get cache stats
        cache = get_cache()
        cache_stats = cache.stats() if hasattr(cache, 'stats') else {}
        
        return JSONResponse(content={
            "database": db_stats,
            "cache": cache_stats,
            "timestamp": datetime.now().isoformat(),
            "status": "healthy"
        })
    except Exception as e:
        logger.error(f"Error getting system stats: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Error obteniendo estadísticas del sistema"}
        )


@router.get("/api/system/health")
async def get_system_health():
    """System health check endpoint"""
    try:
        # Check database connection
        db_stats = get_database_stats()
        db_healthy = db_stats.get('user_count', -1) >= 0
        
        # Check cache
        cache = get_cache()
        cache_healthy = True
        try:
            # Test cache by setting and getting a test value
            test_key = "health_check_" + datetime.now().isoformat()
            cache.set(test_key, "test", 10)
            test_value = cache.get(test_key)
            cache_healthy = test_value == "test"
        except Exception:
            cache_healthy = False
        
        return JSONResponse(content={
            "status": "healthy" if db_healthy and cache_healthy else "degraded",
            "components": {
                "database": "healthy" if db_healthy else "unhealthy",
                "cache": "healthy" if cache_healthy else "unhealthy"
            },
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        )


# Export user preferences functionality
class UserPreferences:
    """User preferences management"""
    
    def __init__(self):
        self.cache = get_cache()
    
    def get_preferences(self, user_id: int) -> Dict:
        """Get user preferences"""
        key = f"user_prefs:{user_id}"
        prefs = self.cache.get(key)
        if prefs is None:
            # Default preferences
            prefs = {
                "theme": "light",
                "language": "es",
                "notifications": True,
                "auto_save": True,
                "default_mode": "general",
                "default_task": "summary",
                "max_text_length": 10000,
                "show_tips": True
            }
            self.cache.set(key, prefs, ttl=86400)  # 24 hours
        return prefs
    
    def update_preferences(self, user_id: int, updates: Dict) -> Dict:
        """Update user preferences"""
        prefs = self.get_preferences(user_id)
        prefs.update(updates)
        
        key = f"user_prefs:{user_id}"
        self.cache.set(key, prefs, ttl=86400)
        
        logger.info(f"Updated preferences for user {user_id}")
        return prefs


user_prefs = UserPreferences()


@router.get("/api/user/preferences")
async def get_user_preferences(request: Request):
    """Get user preferences"""
    user = get_current_user(request)
    if not user:
        return JSONResponse(
            status_code=401,
            content={"error": "No autorizado"}
        )
    
    prefs = user_prefs.get_preferences(user['id'])
    return JSONResponse(content={"preferences": prefs})


@router.post("/api/user/preferences")
async def update_user_preferences(request: Request):
    """Update user preferences"""
    user = get_current_user(request)
    if not user:
        return JSONResponse(
            status_code=401,
            content={"error": "No autorizado"}
        )
    
    try:
        data = await request.json()
        updates = data.get("updates", {})
        
        # Validate updates
        valid_keys = {
            "theme", "language", "notifications", "auto_save",
            "default_mode", "default_task", "max_text_length", "show_tips"
        }
        
        filtered_updates = {k: v for k, v in updates.items() if k in valid_keys}
        
        prefs = user_prefs.update_preferences(user['id'], filtered_updates)
        
        return JSONResponse(content={
            "success": True,
            "preferences": prefs
        })
    except Exception as e:
        logger.error(f"Error updating preferences: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Error actualizando preferencias"}
        )