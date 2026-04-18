"""
Modo Especializado CFIS para NUX-AI

Este módulo implementa funcionalidades específicas para la preparación
del CFIS (Centre de Formació Interdisciplinària Superior) de la UPC.
"""

import json
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import random

from app.config import settings
from app.persistent_cache import persistent_cache

logger = logging.getLogger(__name__)


class CFISStudyMode:
    """Modo de estudio especializado para preparación CFIS"""
    
    def __init__(self):
        # Temas específicos del CFIS
        self.topics = {
            "matematicas": {
                "subtopics": [
                    "algebra",
                    "calculus", 
                    "combinatoria",
                    "teoria_de_numeros",
                    "geometria",
                    "probabilidad"
                ],
                "difficulty_levels": ["basico", "intermedio", "avanzado", "olimpiada"],
                "sources": ["OMC", "IMO", "CFIS_pasados", "UPC_examenes"]
            },
            "fisica": {
                "subtopics": [
                    "mecanica",
                    "electromagnetismo",
                    "termodinamica",
                    "optica",
                    "fisica_moderna"
                ],
                "difficulty_levels": ["basico", "intermedio", "avanzado"],
                "sources": ["Fisica_Olympiad", "CFIS_pasados", "universidad"]
            },
            "logica": {
                "subtopics": ["razonamiento_logico", "pensamiento_critico"],
                "difficulty_levels": ["basico", "avanzado"],
                "sources": ["CFIS_pasados", "test_psicotecnicos"]
            }
        }
        
        # Base de datos de problemas (en memoria por ahora)
        self.problems_database = self._load_problems_database()
        
        # Estadísticas de usuario
        self.user_stats = {}
    
    def _load_problems_database(self) -> Dict:
        """Carga la base de datos de problemas CFIS"""
        # Por ahora, problemas de ejemplo. En el futuro, cargar de archivo JSON
        return {
            "matematicas": {
                "combinatoria": [
                    {
                        "id": "comb_001",
                        "problem": "¿De cuántas maneras se pueden sentar 5 personas en una fila de 5 asientos?",
                        "solution": "5! = 120 maneras",
                        "step_by_step": "Para la primera posición hay 5 opciones, para la segunda 4, tercera 3, cuarta 2, quinta 1. Multiplicando: 5×4×3×2×1 = 120.",
                        "difficulty": "basico",
                        "source": "CFIS_2023",
                        "tags": ["permutaciones", "factorial"]
                    },
                    {
                        "id": "comb_002",
                        "problem": "¿Cuántos números de 3 cifras distintas se pueden formar con los dígitos 1, 2, 3, 4, 5?",
                        "solution": "60 números",
                        "step_by_step": "Para la primera cifra: 5 opciones, segunda: 4 opciones, tercera: 3 opciones. 5×4×3 = 60.",
                        "difficulty": "basico",
                        "source": "OMC",
                        "tags": ["variaciones", "digitos"]
                    }
                ],
                "teoria_de_numeros": [
                    {
                        "id": "num_001",
                        "problem": "Demuestra que el cuadrado de cualquier número impar es de la forma 8k + 1.",
                        "solution": "Sea n = 2m + 1 (impar). n² = (2m + 1)² = 4m² + 4m + 1 = 4m(m + 1) + 1. Como m(m+1) es par, 4m(m+1) es múltiplo de 8.",
                        "step_by_step": "1. Expresar número impar como 2m+1\n2. Elevar al cuadrado\n3. Factorizar\n4. Demostrar que m(m+1) es par\n5. Concluir que es de forma 8k+1",
                        "difficulty": "intermedio",
                        "source": "CFIS_2024",
                        "tags": ["numeros_impares", "demostracion"]
                    }
                ]
            },
            "fisica": {
                "mecanica": [
                    {
                        "id": "mec_001",
                        "problem": "Un coche acelera uniformemente desde 0 a 100 km/h en 10 segundos. Calcula la aceleración y la distancia recorrida.",
                        "solution": "a = 2.78 m/s², d = 138.9 m",
                        "step_by_step": "1. Convertir 100 km/h a m/s: 100 × (1000/3600) = 27.78 m/s\n2. Aceleración: a = Δv/Δt = 27.78/10 = 2.78 m/s²\n3. Distancia: d = (1/2)at² = 0.5 × 2.78 × 10² = 138.9 m",
                        "difficulty": "basico",
                        "source": "Fisica_basica",
                        "tags": ["cinematica", "aceleracion"]
                    }
                ]
            }
        }
    
    def generate_cfis_problem(self, topic: str, subtopic: Optional[str] = None, 
                             difficulty: str = "intermedio") -> Optional[Dict]:
        """
        Genera un problema CFIS basado en el tema y dificultad
        
        Args:
            topic: Tema principal (matematicas, fisica, logica)
            subtopic: Subtema específico
            difficulty: Nivel de dificultad
        
        Returns:
            Diccionario con el problema o None si no hay problemas
        """
        if topic not in self.problems_database:
            logger.warning(f"Tema no encontrado: {topic}")
            return None
        
        topic_problems = self.problems_database[topic]
        
        # Si no se especifica subtopic, elegir uno aleatorio
        if not subtopic:
            subtopic = random.choice(list(topic_problems.keys()))
        
        if subtopic not in topic_problems:
            logger.warning(f"Subtema no encontrado: {subtopic} en {topic}")
            return None
        
        # Filtrar por dificultad
        subtopic_problems = [
            p for p in topic_problems[subtopic] 
            if p.get("difficulty", "intermedio") == difficulty
        ]
        
        if not subtopic_problems:
            # Si no hay problemas de esa dificultad, tomar cualquiera
            subtopic_problems = topic_problems[subtopic]
        
        if not subtopic_problems:
            return None
        
        # Seleccionar problema aleatorio
        problem = random.choice(subtopic_problems)
        
        return {
            "id": problem["id"],
            "problem": problem["problem"],
            "topic": topic,
            "subtopic": subtopic,
            "difficulty": difficulty,
            "source": problem.get("source", "CFIS"),
            "tags": problem.get("tags", []),
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "hints_available": 3
            }
        }
    
    def provide_cfis_solution(self, problem_id: str, show_steps: bool = True) -> Optional[Dict]:
        """
        Proporciona la solución a un problema CFIS
        
        Args:
            problem_id: ID del problema
            show_steps: Mostrar solución paso a paso
        
        Returns:
            Diccionario con solución o None si no se encuentra
        """
        # Buscar en toda la base de datos
        for topic, subtopics in self.problems_database.items():
            for subtopic, problems in subtopics.items():
                for problem in problems:
                    if problem["id"] == problem_id:
                        solution_data = {
                            "problem": problem["problem"],
                            "solution": problem["solution"],
                            "topic": topic,
                            "subtopic": subtopic,
                            "difficulty": problem.get("difficulty", "intermedio"),
                            "source": problem.get("source", "CFIS")
                        }
                        
                        if show_steps and "step_by_step" in problem:
                            solution_data["step_by_step"] = problem["step_by_step"]
                        
                        # Añadir consejos para problemas similares
                        solution_data["tips"] = self._generate_tips(topic, subtopic)
                        
                        return solution_data
        
        logger.warning(f"Problema no encontrado: {problem_id}")
        return None
    
    def _generate_tips(self, topic: str, subtopic: str) -> List[str]:
        """Genera consejos para un tema específico"""
        tips = {
            "matematicas": {
                "combinatoria": [
                    "Identifica si es permutación, combinación o variación",
                    "Considera si los elementos se repiten o no",
                    "Usa el principio de multiplicación para eventos secuenciales",
                    "Para problemas complejos, intenta casos más pequeños primero"
                ],
                "teoria_de_numeros": [
                    "Recuerda propiedades básicas: par×par=par, impar×impar=impar",
                    "Para demostraciones, prueba con casos pequeños primero",
                    "Usa congruencias módulo n para simplificar",
                    "Considera la factorización en primos"
                ],
                "geometria": [
                    "Dibuja siempre un diagrama claro",
                    "Marca ángulos y longitudes conocidas",
                    "Busca triángulos semejantes o congruentes",
                    "Considera usar coordenadas o vectores"
                ]
            },
            "fisica": {
                "mecanica": [
                    "Identifica todas las fuerzas que actúan",
                    "Dibuja un diagrama de cuerpo libre",
                    "Aplica las leyes de Newton adecuadamente",
                    "Verifica las unidades en cada paso"
                ],
                "electromagnetismo": [
                    "Usa la regla de la mano derecha para campos magnéticos",
                    "Recuerda que campos eléctricos van de + a -",
                    "Aplica la ley de Gauss para simetrías",
                    "Considera conservación de energía"
                ]
            }
        }
        
        return tips.get(topic, {}).get(subtopic, [
            "Lee el problema cuidadosamente",
            "Identifica qué te piden exactamente",
            "Anota los datos proporcionados",
            "Busca patrones o simetrías"
        ])
    
    def analyze_user_performance(self, user_id: str, responses: List[Dict]) -> Dict:
        """
        Analiza el desempeño de un usuario en problemas CFIS
        
        Args:
            user_id: ID del usuario
            responses: Lista de respuestas del usuario
        
        Returns:
            Análisis de desempeño
        """
        if not responses:
            return {
                "user_id": user_id,
                "total_problems": 0,
                "message": "No hay datos de desempeño"
            }
        
        # Calcular estadísticas
        total = len(responses)
        correct = sum(1 for r in responses if r.get("correct", False))
        accuracy = (correct / total * 100) if total > 0 else 0
        
        # Análisis por tema
        topic_stats = {}
        for response in responses:
            topic = response.get("topic", "desconocido")
            if topic not in topic_stats:
                topic_stats[topic] = {"total": 0, "correct": 0}
            
            topic_stats[topic]["total"] += 1
            if response.get("correct", False):
                topic_stats[topic]["correct"] += 1
        
        # Calcular accuracy por tema
        for topic, stats in topic_stats.items():
            stats["accuracy"] = (stats["correct"] / stats["total"] * 100) if stats["total"] > 0 else 0
        
        # Identificar fortalezas y debilidades
        strengths = []
        weaknesses = []
        
        for topic, stats in topic_stats.items():
            if stats["accuracy"] >= 70:
                strengths.append({
                    "topic": topic,
                    "accuracy": stats["accuracy"],
                    "problems": stats["total"]
                })
            elif stats["accuracy"] <= 40:
                weaknesses.append({
                    "topic": topic,
                    "accuracy": stats["accuracy"],
                    "problems": stats["total"]
                })
        
        # Recomendaciones de estudio
        recommendations = []
        if weaknesses:
            recommendations.append(f"Enfócate en: {', '.join([w['topic'] for w in weaknesses])}")
        
        if accuracy < 60:
            recommendations.append("Practica más problemas básicos antes de avanzar")
        elif accuracy >= 80:
            recommendations.append("Intenta problemas de mayor dificultad")
        
        # Estimación de preparación CFIS
        cfis_readiness = self._estimate_cfis_readiness(accuracy, total, topic_stats)
        
        return {
            "user_id": user_id,
            "overall": {
                "total_problems": total,
                "correct": correct,
                "accuracy_percent": round(accuracy, 1),
                "cfis_readiness_percent": cfis_readiness
            },
            "by_topic": topic_stats,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "recommendations": recommendations,
            "analysis_date": datetime.now().isoformat()
        }
    
    def _estimate_cfis_readiness(self, accuracy: float, total_problems: int, 
                                topic_stats: Dict) -> float:
        """
        Estima la preparación para el CFIS basado en el desempeño
        
        Args:
            accuracy: Accuracy general
            total_problems: Total de problemas intentados
            topic_stats: Estadísticas por tema
        
        Returns:
            Porcentaje de preparación estimado (0-100)
        """
        if total_problems < 10:
            return min(accuracy, 30)  # Poca data, estimación conservadora
        
        # Ponderar por importancia de temas para CFIS
        topic_weights = {
            "matematicas": 0.5,
            "fisica": 0.3,
            "logica": 0.2
        }
        
        weighted_score = 0
        total_weight = 0
        
        for topic, stats in topic_stats.items():
            weight = topic_weights.get(topic, 0.1)
            topic_accuracy = stats.get("accuracy", 0)
            weighted_score += topic_accuracy * weight
            total_weight += weight
        
        if total_weight > 0:
            readiness = weighted_score / total_weight
        else:
            readiness = accuracy
        
        # Ajustar por cantidad de práctica
        practice_factor = min(total_problems / 100, 1.0)  # Máximo efecto con 100 problemas
        adjusted_readiness = readiness * (0.3 + 0.7 * practice_factor)
        
        return min(adjusted_readiness, 100)
    
    def generate_study_plan(self, user_id: str, days_until_exam: int, 
                           current_level: str = "intermedio") -> Dict:
        """
        Genera un plan de estudio personalizado para CFIS
        
        Args:
            user_id: ID del usuario
            days_until_exam: Días hasta el examen
            current_level: Nivel actual del usuario
        
        Returns:
            Plan de estudio estructurado
        """
        if days_until_exam <= 0:
            return {"error": "Los días hasta el examen deben ser positivos"}
        
        # Distribución de temas según importancia CFIS
        topic_distribution = {
            "matematicas": 0.5,  # 50% del tiempo
            "fisica": 0.3,       # 30% del tiempo
            "logica": 0.2        # 20% del tiempo
        }
        
        # Horas de estudio recomendadas por día
        if days_until_exam > 60:
            hours_per_day = 1  # Preparación larga
        elif days_until_exam > 30:
            hours_per_day = 2  # Preparación media
        elif days_until_exam > 14:
            hours_per_day = 3  # Preparación intensiva
        else:
            hours_per_day = 4  # Últimas semanas
        
        total_hours = days_until_exam * hours_per_day
        
        # Crear plan semanal
        weekly_plan = []
        days = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        
        for week in range(1, (days_until_exam // 7) + 2):
            week_plan = {
                "week": week,
                "focus": f"Semana {week} de preparación",
                "days": []
            }
            
            for day_idx, day_name in enumerate(days):
                if (week - 1) * 7 + day_idx >= days_until_exam:
                    break
                
                # Determinar tema del día (rotación)
                if day_idx % 3 == 0:
                    topic = "matematicas"
                elif day_idx % 3 == 1:
                    topic = "fisica"
                else:
                    topic = "logica"
                
                # Determinar tipo de actividad
                if day_idx == 0:  # Lunes
                    activity = "Nuevos conceptos"
                elif day_idx == 6:  # Domingo
                    activity = "Repaso y simulacro"
                else:
                    activity = "Problemas prácticos"
                
                day_plan = {
                    "day