"""
Rutas para el modo CFIS de NUX-AI
"""

import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional, Dict, List
import json

from app.config import settings
from app.cfis_mode import CFISStudyMode
from app.rate_limiting import smart_rate_limit
from app.persistent_cache import persistent_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cfis", tags=["CFIS Mode"])
cfis_mode = CFISStudyMode()


@router.get("/topics")
@smart_rate_limit(task_type="chat")
async def get_cfis_topics(request: Request):
    """Obtiene los temas disponibles para preparación CFIS"""
    return {
        "topics": cfis_mode.topics,
        "message": "Temas disponibles para preparación CFIS",
        "timestamp": "2026-04-18T09:55:00Z"
    }


@router.get("/generate-problem")
@smart_rate_limit(task_type="math")
async def generate_cfis_problem(
    request: Request,
    topic: str = "matematicas",
    subtopic: Optional[str] = None,
    difficulty: str = "intermedio"
):
    """Genera un problema CFIS"""
    if not settings.CFIS_MODE_ENABLED:
        raise HTTPException(status_code=403, detail="Modo CFIS deshabilitado")
    
    if topic not in cfis_mode.topics:
        raise HTTPException(
            status_code=400, 
            detail=f"Tema no válido. Opciones: {list(cfis_mode.topics.keys())}"
        )
    
    problem = cfis_mode.generate_cfis_problem(topic, subtopic, difficulty)
    
    if not problem:
        raise HTTPException(
            status_code=404, 
            detail="No se pudo generar un problema con los parámetros especificados"
        )
    
    # Cachear el problema generado
    cache_key = f"cfis_problem:{problem['id']}"
    persistent_cache.cache_ai_response(
        query=cache_key,
        response=json.dumps(problem),
        model="cfis_generator",
        task_type="math",
        ttl_hours=24,
        metadata={
            "topic": topic,
            "subtopic": subtopic,
            "difficulty": difficulty,
            "source": "cfis_mode"
        }
    )
    
    return {
        "success": True,
        "problem": problem,
        "instructions": "Resuelve este problema. Puedes pedir ayuda o la solución completa.",
        "cache_info": {
            "cached": True,
            "id": problem['id']
        }
    }


@router.get("/solution/{problem_id}")
@smart_rate_limit(task_type="math")
async def get_cfis_solution(request: Request, problem_id: str, show_steps: bool = True):
    """Obtiene la solución de un problema CFIS"""
    # Primero verificar en cache
    cache_key = f"cfis_solution:{problem_id}"
    cached = persistent_cache.get_cached_response(cache_key)
    
    if cached and settings.CACHE_ENABLED:
        solution_data = json.loads(cached['response'])
        return {
            "success": True,
            "solution": solution_data,
            "cached": True,
            "cache_info": cached
        }
    
    # Si no está en cache, generarla
    solution = cfis_mode.provide_cfis_solution(problem_id, show_steps)
    
    if not solution:
        raise HTTPException(status_code=404, detail="Problema no encontrado")
    
    # Cachear la solución
    persistent_cache.cache_ai_response(
        query=cache_key,
        response=json.dumps(solution),
        model="cfis_solver",
        task_type="math",
        ttl_hours=72,  # Soluciones válidas por 3 días
        metadata={
            "problem_id": problem_id,
            "show_steps": show_steps
        }
    )
    
    return {
        "success": True,
        "solution": solution,
        "cached": False,
        "cache_info": {
            "now_cached": True,
            "ttl_hours": 72
        }
    }


@router.post("/analyze-performance")
@smart_rate_limit(task_type="chat")
async def analyze_cfis_performance(request: Request, user_responses: List[Dict]):
    """Analiza el desempeño en problemas CFIS"""
    if not user_responses:
        raise HTTPException(status_code=400, detail="Se requieren respuestas para analizar")
    
    # Obtener user_id del token si está disponible
    user_id = "anonymous"
    token = request.cookies.get("access_token")
    if token:
        # TODO: Decodificar token para obtener user_id real
        user_id = f"user_{hash(token) % 10000}"
    
    analysis = cfis_mode.analyze_user_performance(user_id, user_responses)
    
    # Cachear el análisis
    cache_key = f"cfis_analysis:{user_id}"
    persistent_cache.cache_ai_response(
        query=cache_key,
        response=json.dumps(analysis),
        model="cfis_analyzer",
        task_type="analytics",
        ttl_hours=6,  # Análisis válido por 6 horas
        metadata={
            "user_id": user_id,
            "response_count": len(user_responses)
        }
    )
    
    return {
        "success": True,
        "analysis": analysis,
        "recommendations": analysis.get("recommendations", []),
        "next_steps": [
            "Practica tus temas débiles",
            "Intenta problemas de mayor dificultad",
            "Realiza simulacros completos"
        ]
    }


@router.get("/study-plan")
@smart_rate_limit(task_type="chat")
async def generate_study_plan(
    request: Request,
    days_until_exam: int = 30,
    current_level: str = "intermedio"
):
    """Genera un plan de estudio personalizado para CFIS"""
    if days_until_exam <= 0:
        raise HTTPException(status_code=400, detail="Los días hasta el examen deben ser positivos")
    
    if days_until_exam > 365:
        raise HTTPException(status_code=400, detail="El plan máximo es de 1 año")
    
    # Obtener user_id
    user_id = "anonymous"
    token = request.cookies.get("access_token")
    if token:
        user_id = f"user_{hash(token) % 10000}"
    
    # Generar plan
    study_plan = cfis_mode.generate_study_plan(user_id, days_until_exam, current_level)
    
    # Cachear el plan
    cache_key = f"cfis_study_plan:{user_id}:{days_until_exam}:{current_level}"
    persistent_cache.cache_ai_response(
        query=cache_key,
        response=json.dumps(study_plan),
        model="cfis_planner",
        task_type="planning",
        ttl_hours=24,
        metadata={
            "user_id": user_id,
            "days_until_exam": days_until_exam,
            "current_level": current_level
        }
    )
    
    return {
        "success": True,
        "study_plan": study_plan,
        "summary": f"Plan de {days_until_exam} días para nivel {current_level}",
        "tips": [
            "Sigue el plan consistentemente",
            "Ajusta el ritmo según tu progreso",
            "Toma descansos regulares",
            "Revisa temas anteriores regularmente"
        ]
    }


@router.get("/tips/{topic}")
@smart_rate_limit(task_type="chat")
async def get_cfis_tips(request: Request, topic: str, subtopic: Optional[str] = None):
    """Obtiene consejos para un tema específico de CFIS"""
    if topic not in cfis_mode.topics:
        raise HTTPException(
            status_code=400, 
            detail=f"Tema no válido. Opciones: {list(cfis_mode.topics.keys())}"
        )
    
    tips = cfis_mode._generate_tips(topic, subtopic or "")
    
    return {
        "success": True,
        "topic": topic,
        "subtopic": subtopic,
        "tips": tips,
        "count": len(tips)
    }


@router.get("/stats")
async def get_cfis_stats(request: Request):
    """Obtiene estadísticas del modo CFIS"""
    # Contar problemas por tema
    problem_counts = {}
    for topic, subtopics in cfis_mode.problems_database.items():
        total = 0
        for subtopic, problems in subtopics.items():
            total += len(problems)
        problem_counts[topic] = total
    
    # Obtener estadísticas de cache
    cache_stats = persistent_cache.get_cache_stats()
    
    return {
        "success": True,
        "cfis_mode": {
            "enabled": settings.CFIS_MODE_ENABLED,
            "topics_available": list(cfis_mode.topics.keys()),
            "total_problems": sum(problem_counts.values()),
            "problems_by_topic": problem_counts
        },
        "cache": cache_stats,
        "rate_limiting": {
            "enabled": True,
            "strategy": "intelligent_per_user"
        },
        "timestamp": "2026-04-18T09:55:00Z"
    }