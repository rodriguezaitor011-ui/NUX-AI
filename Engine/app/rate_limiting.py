"""
Sistema de Rate Limiting Inteligente para NUX-AI

Este módulo implementa rate limiting por usuario y tipo de tarea,
con límites diferenciados para usuarios free y premium.
"""

import time
from typing import Dict, Optional, Tuple
from collections import defaultdict
import logging
from datetime import datetime, timedelta

from app.config import settings

logger = logging.getLogger(__name__)


class RateLimitConfig:
    """Configuración de límites por tipo de usuario y tarea"""
    
    # Límites para usuarios free (por hora)
    FREE_LIMITS = {
        "chat": 60,          # 60 mensajes por hora (1 por minuto)
        "document": 10,      # 10 documentos por hora
        "math": 30,          # 30 problemas matemáticos por hora
        "ocr": 5,            # 5 OCR por hora
        "notebook": 20       # 20 operaciones de notebook por hora
    }
    
    # Límites para usuarios premium (por hora)
    PREMIUM_LIMITS = {
        "chat": 1000,        # 1000 mensajes por hora (~16 por minuto)
        "document": 100,     # 100 documentos por hora
        "math": 500,         # 500 problemas matemáticos por hora
        "ocr": 50,           # 50 OCR por hora
        "notebook": 200      # 200 operaciones de notebook por hora
    }
    
    # Límites para administradores (prácticamente ilimitados)
    ADMIN_LIMITS = {
        "chat": 10000,
        "document": 1000,
        "math": 5000,
        "ocr": 500,
        "notebook": 1000
    }


class RateLimitTracker:
    """Rastrea el uso de API por usuario y tipo de tarea"""
    
    def __init__(self):
        # Estructura: user_id -> task_type -> [(timestamp, count)]
        self.usage: Dict[str, Dict[str, list]] = defaultdict(lambda: defaultdict(list))
        self.user_types: Dict[str, str] = {}  # user_id -> "free", "premium", "admin"
        
    def get_user_type(self, user_id: Optional[str] = None) -> str:
        """Determina el tipo de usuario"""
        if not user_id:
            return "free"
        
        # Por ahora, todos son free. En el futuro, consultar base de datos
        if user_id in self.user_types:
            return self.user_types[user_id]
        
        # TODO: Consultar base de datos para determinar si es premium/admin
        # Por ahora, asumimos free
        return "free"
    
    def get_limits(self, user_type: str) -> Dict[str, int]:
        """Obtiene los límites para un tipo de usuario"""
        if user_type == "premium":
            return RateLimitConfig.PREMIUM_LIMITS
        elif user_type == "admin":
            return RateLimitConfig.ADMIN_LIMITS
        else:
            return RateLimitConfig.FREE_LIMITS
    
    def check_rate_limit(self, user_id: Optional[str], task_type: str) -> Tuple[bool, Dict]:
        """
        Verifica si el usuario puede realizar una tarea
        
        Returns:
            Tuple[bool, Dict]: (permitido, información de límites)
        """
        user_type = self.get_user_type(user_id)
        limits = self.get_limits(user_type)
        
        if task_type not in limits:
            logger.warning(f"Tipo de tarea desconocido: {task_type}")
            return True, {"allowed": True, "reason": "unknown_task_type"}
        
        # Limpiar registros antiguos (más de 1 hora)
        current_time = time.time()
        one_hour_ago = current_time - 3600
        
        if user_id:
            # Filtrar registros antiguos
            self.usage[user_id][task_type] = [
                ts for ts in self.usage[user_id][task_type] if ts > one_hour_ago
            ]
            
            # Contar usos en la última hora
            usage_count = len(self.usage[user_id][task_type])
            limit = limits[task_type]
            
            if usage_count >= limit:
                # Calcular tiempo hasta que se resetee
                oldest_timestamp = min(self.usage[user_id][task_type]) if self.usage[user_id][task_type] else current_time
                reset_time = oldest_timestamp + 3600
                wait_seconds = max(0, reset_time - current_time)
                
                return False, {
                    "allowed": False,
                    "reason": "rate_limit_exceeded",
                    "user_type": user_type,
                    "task_type": task_type,
                    "usage": usage_count,
                    "limit": limit,
                    "reset_in_seconds": int(wait_seconds),
                    "reset_at": datetime.fromtimestamp(reset_time).isoformat()
                }
            
            # Registrar nuevo uso
            self.usage[user_id][task_type].append(current_time)
            
            return True, {
                "allowed": True,
                "user_type": user_type,
                "task_type": task_type,
                "usage": usage_count + 1,
                "limit": limit,
                "remaining": limit - (usage_count + 1)
            }
        else:
            # Usuario no autenticado - límites más estrictos
            anonymous_key = f"anonymous_{task_type}"
            self.usage[anonymous_key][task_type] = [
                ts for ts in self.usage[anonymous_key][task_type] if ts > one_hour_ago
            ]
            
            usage_count = len(self.usage[anonymous_key][task_type])
            limit = limits[task_type] // 2  # Límites más estrictos para anónimos
            
            if usage_count >= limit:
                return False, {
                    "allowed": False,
                    "reason": "rate_limit_exceeded_anonymous",
                    "task_type": task_type,
                    "usage": usage_count,
                    "limit": limit,
                    "message": "Por favor, regístrate para obtener límites más altos"
                }
            
            self.usage[anonymous_key][task_type].append(current_time)
            return True, {
                "allowed": True,
                "user_type": "anonymous",
                "task_type": task_type,
                "usage": usage_count + 1,
                "limit": limit,
                "remaining": limit - (usage_count + 1)
            }
    
    def get_usage_stats(self, user_id: Optional[str] = None) -> Dict:
        """Obtiene estadísticas de uso para un usuario"""
        stats = {}
        user_type = self.get_user_type(user_id)
        limits = self.get_limits(user_type)
        
        for task_type in limits.keys():
            if user_id:
                # Limpiar registros antiguos
                current_time = time.time()
                one_hour_ago = current_time - 3600
                self.usage[user_id][task_type] = [
                    ts for ts in self.usage[user_id][task_type] if ts > one_hour_ago
                ]
                usage_count = len(self.usage[user_id][task_type])
            else:
                anonymous_key = f"anonymous_{task_type}"
                usage_count = len(self.usage[anonymous_key][task_type])
            
            stats[task_type] = {
                "used": usage_count,
                "limit": limits[task_type],
                "remaining": limits[task_type] - usage_count,
                "percentage": (usage_count / limits[task_type]) * 100 if limits[task_type] > 0 else 0
            }
        
        return {
            "user_type": user_type,
            "stats": stats,
            "timestamp": datetime.now().isoformat()
        }


# Instancia global del tracker
rate_limit_tracker = RateLimitTracker()


def get_task_type_from_request(request) -> str:
    """Determina el tipo de tarea basado en la ruta y método de la request"""
    path = request.url.path
    method = request.method
    
    if "/api/chat" in path or "/chat" in path:
        return "chat"
    elif "/api/process-document" in path or "/upload" in path:
        return "document"
    elif "/api/solve-math" in path or "math" in path.lower():
        return "math"
    elif "/api/ocr" in path or "ocr" in path.lower():
        return "ocr"
    elif "/api/notebook" in path or "/notebook" in path:
        return "notebook"
    else:
        return "chat"  # Por defecto


# Decorador para rate limiting inteligente
def smart_rate_limit(task_type: Optional[str] = None):
    """
    Decorador para aplicar rate limiting inteligente
    
    Args:
        task_type: Tipo de tarea (si no se proporciona, se infiere de la request)
    """
    def decorator(func):
        async def wrapper(request: Request, *args, **kwargs):
            # Obtener user_id si está autenticado
            user_id = None
            token = request.cookies.get("access_token")
            if token:
                # TODO: Decodificar token para obtener user_id
                # Por ahora, usar IP como identificador temporal
                user_id = request.client.host
            
            # Determinar tipo de tarea
            actual_task_type = task_type or get_task_type_from_request(request)
            
            # Verificar rate limit
            allowed, limit_info = rate_limit_tracker.check_rate_limit(user_id, actual_task_type)
            
            if not allowed:
                logger.warning(f"Rate limit excedido: {limit_info}")
                
                # Añadir headers de rate limiting (estándar HTTP)
                headers = {
                    "X-RateLimit-Limit": str(limit_info.get("limit", 0)),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(limit_info.get("reset_in_seconds", 3600)),
                    "X-RateLimit-UserType": limit_info.get("user_type", "unknown"),
                    "X-RateLimit-TaskType": actual_task_type
                }
                
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Rate limit exceeded",
                        "detail": limit_info.get("message", "Too many requests"),
                        "retry_after": limit_info.get("reset_in_seconds", 3600),
                        "limits": limit_info
                    },
                    headers=headers
                )
            
            # Añadir headers de rate limiting para respuestas exitosas
            request.state.rate_limit_info = limit_info
            
            # Ejecutar la función
            response = await func(request, *args, **kwargs)
            
            # Añadir headers de rate limiting a la respuesta
            if hasattr(response, 'headers'):
                response.headers["X-RateLimit-Limit"] = str(limit_info.get("limit", 0))
                response.headers["X-RateLimit-Remaining"] = str(limit_info.get("remaining", 0))
                response.headers["X-RateLimit-UserType"] = limit_info.get("user_type", "unknown")
                response.headers["X-RateLimit-TaskType"] = actual_task_type
            
            return response
        
        return wrapper
    
    return decorator