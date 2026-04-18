"""
Cache Persistente para NUX-AI

Este módulo implementa un sistema de cache persistente usando SQLite
para reducir llamadas a APIs externas y mejorar el rendimiento.
"""

import sqlite3
import json
import hashlib
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Any, Dict, List, Tuple
import pickle
import zlib

logger = logging.getLogger(__name__)


class PersistentCache:
    """Cache persistente usando SQLite"""
    
    def __init__(self, db_path: str = "nuxai_cache.db"):
        self.db_path = db_path
        self.conn = None
        self.init_db()
        
    def init_db(self):
        """Inicializa la base de datos SQLite"""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            
            cursor = self.conn.cursor()
            
            # Tabla para cache de respuestas de IA
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ai_responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_hash TEXT UNIQUE NOT NULL,
                    query_text TEXT NOT NULL,
                    response_text TEXT NOT NULL,
                    model_used TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    confidence_score REAL DEFAULT 1.0,
                    usage_count INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    metadata TEXT
                )
            ''')
            
            # Tabla para cache de problemas matemáticos
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS math_solutions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    problem_hash TEXT UNIQUE NOT NULL,
                    problem_text TEXT NOT NULL,
                    solution_text TEXT NOT NULL,
                    step_by_step TEXT,
                    wolfram_verified BOOLEAN DEFAULT FALSE,
                    verification_score REAL DEFAULT 0.0,
                    topic TEXT,
                    difficulty TEXT,
                    usage_count INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Tabla para cache de documentos procesados
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS processed_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_hash TEXT UNIQUE NOT NULL,
                    document_name TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    processed_content TEXT,
                    summary TEXT,
                    key_points TEXT,
                    word_count INTEGER,
                    processing_time REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Tabla para estadísticas de cache
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cache_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE UNIQUE NOT NULL,
                    hits INTEGER DEFAULT 0,
                    misses INTEGER DEFAULT 0,
                    savings_usd REAL DEFAULT 0.0,
                    total_queries INTEGER DEFAULT 0,
                    avg_response_time REAL DEFAULT 0.0
                )
            ''')
            
            # Índices para mejorar el rendimiento
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_query_hash ON ai_responses(query_hash)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_expires_at ON ai_responses(expires_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_math_hash ON math_solutions(problem_hash)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_doc_hash ON processed_documents(document_hash)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_cache_date ON cache_stats(date)')
            
            self.conn.commit()
            logger.info(f"Cache persistente inicializado en {self.db_path}")
            
        except Exception as e:
            logger.error(f"Error al inicializar cache persistente: {e}")
            raise
    
    def _get_hash(self, text: str) -> str:
        """Genera hash MD5 de un texto"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def _compress(self, data: str) -> bytes:
        """Comprime texto para ahorrar espacio"""
        return zlib.compress(data.encode('utf-8'))
    
    def _decompress(self, compressed_data: bytes) -> str:
        """Descomprime texto"""
        return zlib.decompress(compressed_data).decode('utf-8')
    
    def cache_ai_response(self, query: str, response: str, model: str, 
                         task_type: str = "general", ttl_hours: int = 24,
                         confidence: float = 1.0, metadata: Optional[Dict] = None) -> str:
        """
        Cachea una respuesta de IA
        
        Args:
            query: Texto de la consulta
            response: Respuesta de la IA
            model: Modelo usado
            task_type: Tipo de tarea (chat, math, document, etc.)
            ttl_hours: Tiempo de vida en horas
            confidence: Puntuación de confianza (0.0-1.0)
            metadata: Metadatos adicionales
        
        Returns:
            Hash de la consulta
        """
        query_hash = self._get_hash(query)
        
        try:
            cursor = self.conn.cursor()
            
            # Verificar si ya existe
            cursor.execute(
                'SELECT id, usage_count FROM ai_responses WHERE query_hash = ?',
                (query_hash,)
            )
            existing = cursor.fetchone()
            
            expires_at = datetime.now() + timedelta(hours=ttl_hours)
            metadata_json = json.dumps(metadata) if metadata else None
            
            if existing:
                # Actualizar registro existente
                cursor.execute('''
                    UPDATE ai_responses 
                    SET response_text = ?, model_used = ?, task_type = ?,
                        confidence_score = ?, last_accessed = CURRENT_TIMESTAMP,
                        expires_at = ?, metadata = ?, usage_count = usage_count + 1
                    WHERE query_hash = ?
                ''', (response, model, task_type, confidence, 
                     expires_at.isoformat(), metadata_json, query_hash))
            else:
                # Insertar nuevo registro
                cursor.execute('''
                    INSERT INTO ai_responses 
                    (query_hash, query_text, response_text, model_used, task_type,
                     confidence_score, expires_at, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (query_hash, query, response, model, task_type,
                     confidence, expires_at.isoformat(), metadata_json))
            
            self.conn.commit()
            
            # Actualizar estadísticas
            self._update_stats(hit=False)  # Es un miss porque estamos guardando
            
            logger.debug(f"Respuesta cacheada: {query_hash[:8]}... ({task_type})")
            return query_hash
            
        except Exception as e:
            logger.error(f"Error al cachear respuesta: {e}")
            return ""
    
    def get_cached_response(self, query: str) -> Optional[Dict]:
        """
        Obtiene una respuesta cacheada
        
        Args:
            query: Texto de la consulta
        
        Returns:
            Diccionario con respuesta o None si no existe
        """
        query_hash = self._get_hash(query)
        
        try:
            cursor = self.conn.cursor()
            
            cursor.execute('''
                SELECT response_text, model_used, task_type, confidence_score,
                       usage_count, created_at, expires_at, metadata
                FROM ai_responses 
                WHERE query_hash = ? 
                AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            ''', (query_hash,))
            
            result = cursor.fetchone()
            
            if result:
                # Actualizar last_accessed y usage_count
                cursor.execute('''
                    UPDATE ai_responses 
                    SET last_accessed = CURRENT_TIMESTAMP, usage_count = usage_count + 1
                    WHERE query_hash = ?
                ''', (query_hash,))
                self.conn.commit()
                
                # Actualizar estadísticas
                self._update_stats(hit=True)
                
                metadata = json.loads(result['metadata']) if result['metadata'] else {}
                
                logger.debug(f"Cache hit: {query_hash[:8]}... (usos: {result['usage_count']})")
                return {
                    'response': result['response_text'],
                    'model': result['model_used'],
                    'task_type': result['task_type'],
                    'confidence': result['confidence_score'],
                    'usage_count': result['usage_count'],
                    'created_at': result['created_at'],
                    'expires_at': result['expires_at'],
                    'metadata': metadata,
                    'cached': True
                }
            else:
                # Actualizar estadísticas
                self._update_stats(hit=False)
                return None
                
        except Exception as e:
            logger.error(f"Error al obtener respuesta cacheada: {e}")
            return None
    
    def cache_math_solution(self, problem: str, solution: str, step_by_step: Optional[str] = None,
                           wolfram_verified: bool = False, verification_score: float = 0.0,
                           topic: Optional[str] = None, difficulty: Optional[str] = None) -> str:
        """
        Cachea una solución matemática
        
        Args:
            problem: Texto del problema
            solution: Solución
            step_by_step: Solución paso a paso
            wolfram_verified: Verificada con Wolfram Alpha
            verification_score: Puntuación de verificación
            topic: Tema matemático
            difficulty: Dificultad
        
        Returns:
            Hash del problema
        """
        problem_hash = self._get_hash(problem)
        
        try:
            cursor = self.conn.cursor()
            
            cursor.execute(
                'SELECT id FROM math_solutions WHERE problem_hash = ?',
                (problem_hash,)
            )
            
            if cursor.fetchone():
                # Actualizar
                cursor.execute('''
                    UPDATE math_solutions 
                    SET solution_text = ?, step_by_step = ?, wolfram_verified = ?,
                        verification_score = ?, topic = ?, difficulty = ?,
                        last_accessed = CURRENT_TIMESTAMP, usage_count = usage_count + 1
                    WHERE problem_hash = ?
                ''', (solution, step_by_step, wolfram_verified, verification_score,
                     topic, difficulty, problem_hash))
            else:
                # Insertar
                cursor.execute('''
                    INSERT INTO math_solutions 
                    (problem_hash, problem_text, solution_text, step_by_step,
                     wolfram_verified, verification_score, topic, difficulty)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (problem_hash, problem, solution, step_by_step,
                     wolfram_verified, verification_score, topic, difficulty))
            
            self.conn.commit()
            logger.debug(f"Solución matemática cacheada: {problem_hash[:8]}...")
            return problem_hash
            
        except Exception as e:
            logger.error(f"Error al cachear solución matemática: {e}")
            return ""
    
    def get_cached_math_solution(self, problem: str) -> Optional[Dict]:
        """
        Obtiene una solución matemática cacheada
        
        Args:
            problem: Texto del problema
        
        Returns:
            Diccionario con solución o None si no existe
        """
        problem_hash = self._get_hash(problem)
        
        try:
            cursor = self.conn.cursor()
            
            cursor.execute('''
                SELECT solution_text, step_by_step, wolfram_verified,
                       verification_score, topic, difficulty, usage_count,
                       created_at
                FROM math_solutions 
                WHERE problem_hash = ?
            ''', (problem_hash,))
            
            result = cursor.fetchone()
            
            if result:
                # Actualizar last_accessed
                cursor.execute('''
                    UPDATE math_solutions 
                    SET last_accessed = CURRENT_TIMESTAMP, usage_count = usage_count + 1
                    WHERE problem_hash = ?
                ''', (problem_hash,))
                self.conn.commit()
                
                return {
                    'solution': result['solution_text'],
                    'step_by_step': result['step_by_step'],
                    'wolfram_verified': bool(result['wolfram_verified']),
                    'verification_score': result['verification_score'],
                    'topic': result['topic'],
                    'difficulty': result['difficulty'],
                    'usage_count': result['usage_count'],
                    'created_at': result['created_at'],
                    'cached': True
                }
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error al obtener solución matemática cacheada: {e}")
            return None
    
    def _update_stats(self, hit: bool):
        """Actualiza estadísticas de cache"""
        try:
            today = datetime.now().date().isoformat()
            cursor = self.conn.cursor()
            
            # Verificar si ya hay estadísticas para hoy
            cursor.execute(
                'SELECT id FROM cache_stats WHERE date = ?',
                (today,)
            )
            
            if cursor.fetchone():
                # Actualizar
                if hit:
                    cursor.execute('''
                        UPDATE cache_stats 
                        SET hits = hits + 1, total_queries = total_queries + 1
                        WHERE date = ?
                    ''', (today,))
                else:
                    cursor.execute('''
                        UPDATE cache_stats 
                        SET misses = misses + 1, total_queries = total_queries + 1
                        WHERE date = ?
                    ''', (today,))
            else:
                # Insertar
                if hit:
                    cursor.execute('''
                        INSERT INTO cache_stats (date, hits, misses, total_queries)
                        VALUES (?, 1, 0, 1)
                    ''', (today,))
                else:
                    cursor.execute('''
                        INSERT INTO cache_stats (date, hits, misses, total_queries)
                        VALUES (?, 0, 1, 1)
                    ''', (today,))
            
            self.conn.commit()
            
        except Exception as e:
            logger.error(f"Error al actualizar estadísticas: {e}")
    
    def get_cache_stats(self, days: int = 7) -> Dict:
        """
        Obtiene estadísticas del cache
        
        Args:
            days: Número de días a incluir
        
        Returns:
            Diccionario con estadísticas
        """
        try:
            cursor = self.conn.cursor()
            
            # Estadísticas generales
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_responses,
                    SUM(usage_count) as total_uses,
                    AVG(confidence_score) as avg_confidence
                FROM ai_responses 
                WHERE expires_at > CURRENT_TIMESTAMP OR expires_at IS NULL
            ''')
            ai_stats = cursor.fetchone()
            
            cursor.execute('SELECT COUNT(*) as total_math FROM math_solutions')
            math_stats = cursor.fetchone()
            
            cursor.execute('SELECT COUNT(*) as total_docs FROM processed_documents')
            doc_stats = cursor.fetchone()
            
            # Estadísticas de hit rate
            start_date = (datetime.now() - timedelta(days=days)).date().isoformat()
            cursor.execute('''
                SELECT 
                    SUM(hits) as total_hits,
                    SUM(misses) as total_misses,
                    SUM(total_queries) as total_queries
                FROM cache_stats 
                WHERE date >= ?
            ''', (start_date,))
            hit_stats = cursor.fetchone()
            
            total_hits = hit_stats['total_hits'] or 0
            total_misses = hit_stats['total_misses'] or 0
            total_queries = hit_stats['total_queries'] or 0
            
            hit_rate = (total_hits / total_queries * 100) if total_queries > 0 else 0
            
            return {
                'ai_responses': {
                    'total': ai_stats['total_responses'] or 0,
                    'total_uses': ai_stats['total_uses'] or 0,
                    'avg_confidence': ai_stats['avg_confidence'] or 0
                },
                'math_solutions': {
                    'total': math_stats['total_math'] or 0
                },
                'processed_documents': {
                    'total': doc_stats['total_docs'] or 0
                },
                'performance': {
                    'hit_rate_percent': round(hit_rate, 2),
                    'total_hits': total_hits,
                    'total_misses': total_misses,
                    'total_queries': total_queries
                },
                'estimated_savings': {
                    'api_calls_saved': total_hits,
                    # Estimación: cada hit ahorra ~$0.001 en APIs
                    'usd_saved': round(total_hits * 0.001, 4)
                },
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error al obtener estadísticas: {e}")
            return {}
    
    def cleanup_expired(self) -> int:
        """
        Limpia entradas expiradas del cache
        
        Returns:
            Número de entradas eliminadas
        """
        try:
            cursor = self.conn.cursor()
            
            # Eliminar respuestas AI expiradas
            cursor.execute('''
                DELETE FROM ai_responses 
                WHERE expires_at IS NOT NULL AND expires_at <= CURRENT_TIMESTAMP
            ''')
            ai_deleted = cursor.rowcount
            
            # Eliminar documentos no accedidos en 30 días
            thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
            cursor.execute('''
                DELETE FROM processed_documents 
                WHERE last_accessed <= ?
            ''', (thirty_days_ago,))
            docs_deleted = cursor.rowcount
            
            self.conn.commit()
            
            total_deleted = ai_deleted + docs_deleted
            logger.info(f"Cache cleanup: {total_deleted} entradas eliminadas")
            
            return total_deleted
            
        except Exception as e:
            logger.error(f"Error en cleanup: {e}")
            return 0
    
    def close(self):
        """Cierra la conexión a la base de datos"""
        if self.conn:
            self.conn.close()


# Instancia global del cache
persistent_cache = PersistentCache()