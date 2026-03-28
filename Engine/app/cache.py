"""
Cache module with support for in-memory and Redis caching.
Provides a unified interface for caching with fallback strategies.
"""

import logging
import time
import json
import pickle
from typing import Optional, Any, Dict, List, Union
from collections import OrderedDict
from datetime import datetime, timedelta
import hashlib

logger = logging.getLogger(__name__)

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis no disponible. Usando cache en memoria.")


class CacheBackend:
    """Base class for cache backends"""
    
    def get(self, key: str) -> Optional[Any]:
        raise NotImplementedError
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        raise NotImplementedError
    
    def delete(self, key: str) -> bool:
        raise NotImplementedError
    
    def exists(self, key: str) -> bool:
        raise NotImplementedError
    
    def clear(self) -> bool:
        raise NotImplementedError
    
    def keys(self, pattern: str = "*") -> List[str]:
        raise NotImplementedError


class MemoryCache(CacheBackend):
    """In-memory cache with LRU eviction and TTL support"""
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 3600):
        self.cache = OrderedDict()
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.hits = 0
        self.misses = 0
        self.evictions = 0
    
    def _clean_expired(self):
        """Remove expired items from cache"""
        expired_keys = []
        current_time = time.time()
        
        for key, item in self.cache.items():
            if current_time - item['timestamp'] > item['ttl']:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cache[key]
    
    def get(self, key: str) -> Optional[Any]:
        self._clean_expired()
        
        if key in self.cache:
            item = self.cache[key]
            # Move to end (recently used)
            self.cache.move_to_end(key)
            self.hits += 1
            return item['value']
        
        self.misses += 1
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        self._clean_expired()
        
        # Evict if cache is full (LRU)
        if len(self.cache) >= self.max_size:
            # Remove oldest item
            self.cache.popitem(last=False)
            self.evictions += 1
        
        ttl_value = ttl if ttl is not None else self.default_ttl
        self.cache[key] = {
            'value': value,
            'timestamp': time.time(),
            'ttl': ttl_value
        }
        
        # Move to end (recently used)
        self.cache.move_to_end(key)
        return True
    
    def delete(self, key: str) -> bool:
        if key in self.cache:
            del self.cache[key]
            return True
        return False
    
    def exists(self, key: str) -> bool:
        self._clean_expired()
        return key in self.cache
    
    def clear(self) -> bool:
        self.cache.clear()
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        return True
    
    def keys(self, pattern: str = "*") -> List[str]:
        self._clean_expired()
        if pattern == "*":
            return list(self.cache.keys())
        
        # Simple pattern matching (supports * at end only)
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return [k for k in self.cache.keys() if k.startswith(prefix)]
        
        return [k for k in self.cache.keys() if k == pattern]
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        self._clean_expired()
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0
        
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': hit_rate,
            'evictions': self.evictions,
            'default_ttl': self.default_ttl
        }


class RedisCache(CacheBackend):
    """Redis cache backend"""
    
    def __init__(self, host: str = "localhost", port: int = 6379, 
                 db: int = 0, password: Optional[str] = None,
                 default_ttl: int = 3600):
        if not REDIS_AVAILABLE:
            raise ImportError("Redis no está instalado. Instala con: pip install redis")
        
        self.client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=False,  # We'll handle encoding/decoding
            socket_timeout=5,
            socket_connect_timeout=5,
            retry_on_timeout=True
        )
        self.default_ttl = default_ttl
        
        # Test connection
        try:
            self.client.ping()
            logger.info("✅ Conectado a Redis")
        except redis.ConnectionError as e:
            logger.error(f"❌ Error conectando a Redis: {e}")
            raise
    
    def _serialize(self, value: Any) -> bytes:
        """Serialize value for Redis storage"""
        try:
            # Try JSON first for simple types
            return json.dumps(value).encode('utf-8')
        except (TypeError, ValueError):
            # Fall back to pickle for complex objects
            return pickle.dumps(value)
    
    def _deserialize(self, data: bytes) -> Any:
        """Deserialize value from Redis"""
        if not data:
            return None
        
        try:
            # Try JSON first
            return json.loads(data.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            try:
                # Fall back to pickle
                return pickle.loads(data)
            except pickle.UnpicklingError:
                logger.warning("No se pudo deserializar dato de Redis")
                return None
    
    def get(self, key: str) -> Optional[Any]:
        try:
            data = self.client.get(key)
            if data is None:
                return None
            return self._deserialize(data)
        except redis.RedisError as e:
            logger.error(f"Error obteniendo de Redis: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        try:
            serialized = self._serialize(value)
            ttl_value = ttl if ttl is not None else self.default_ttl
            
            if ttl_value > 0:
                self.client.setex(key, ttl_value, serialized)
            else:
                self.client.set(key, serialized)
            
            return True
        except redis.RedisError as e:
            logger.error(f"Error guardando en Redis: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        try:
            result = self.client.delete(key)
            return result > 0
        except redis.RedisError as e:
            logger.error(f"Error eliminando de Redis: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        try:
            return self.client.exists(key) > 0
        except redis.RedisError as e:
            logger.error(f"Error verificando existencia en Redis: {e}")
            return False
    
    def clear(self) -> bool:
        try:
            self.client.flushdb()
            return True
        except redis.RedisError as e:
            logger.error(f"Error limpiando Redis: {e}")
            return False
    
    def keys(self, pattern: str = "*") -> List[str]:
        try:
            keys = self.client.keys(pattern)
            return [k.decode('utf-8') if isinstance(k, bytes) else k for k in keys]
        except redis.RedisError as e:
            logger.error(f"Error obteniendo claves de Redis: {e}")
            return []
    
    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment a counter in Redis"""
        try:
            return self.client.incrby(key, amount)
        except redis.RedisError as e:
            logger.error(f"Error incrementando en Redis: {e}")
            return None
    
    def get_ttl(self, key: str) -> Optional[int]:
        """Get remaining TTL for a key"""
        try:
            ttl = self.client.ttl(key)
            return ttl if ttl >= 0 else None
        except redis.RedisError as e:
            logger.error(f"Error obteniendo TTL de Redis: {e}")
            return None


class HybridCache(CacheBackend):
    """
    Hybrid cache that uses both memory and Redis.
    Memory cache for fast access, Redis for persistence and sharing between processes.
    """
    
    def __init__(self, memory_max_size: int = 1000, 
                 memory_ttl: int = 300,  # 5 minutes for memory
                 redis_host: str = "localhost",
                 redis_port: int = 6379,
                 redis_db: int = 0,
                 redis_password: Optional[str] = None,
                 redis_ttl: int = 3600):  # 1 hour for Redis
        
        self.memory_cache = MemoryCache(max_size=memory_max_size, default_ttl=memory_ttl)
        
        if REDIS_AVAILABLE:
            try:
                self.redis_cache = RedisCache(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    password=redis_password,
                    default_ttl=redis_ttl
                )
                self.redis_enabled = True
            except (ImportError, redis.ConnectionError):
                self.redis_enabled = False
                logger.warning("Redis no disponible. Usando solo cache en memoria.")
        else:
            self.redis_enabled = False
    
    def get(self, key: str) -> Optional[Any]:
        # Try memory cache first
        value = self.memory_cache.get(key)
        if value is not None:
            return value
        
        # Try Redis if enabled
        if self.redis_enabled:
            value = self.redis_cache.get(key)
            if value is not None:
                # Populate memory cache for future fast access
                self.memory_cache.set(key, value)
                return value
        
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        # Set in memory cache
        memory_success = self.memory_cache.set(key, value, ttl)
        
        # Set in Redis if enabled
        redis_success = True
        if self.redis_enabled:
            redis_success = self.redis_cache.set(key, value, ttl)
        
        return memory_success and redis_success
    
    def delete(self, key: str) -> bool:
        memory_success = self.memory_cache.delete(key)
        
        redis_success = True
        if self.redis_enabled:
            redis_success = self.redis_cache.delete(key)
        
        return memory_success and redis_success
    
    def exists(self, key: str) -> bool:
        if self.memory_cache.exists(key):
            return True
        
        if self.redis_enabled:
            return self.redis_cache.exists(key)
        
        return False
    
    def clear(self) -> bool:
        memory_success = self.memory_cache.clear()
        
        redis_success = True
        if self.redis_enabled:
            redis_success = self.redis_cache.clear()
        
        return memory_success and redis_success
    
    def keys(self, pattern: str = "*") -> List[str]:
        memory_keys = set(self.memory_cache.keys(pattern))
        
        if self.redis_enabled:
            redis_keys = set(self.redis_cache.keys(pattern))
            memory_keys.update(redis_keys)
        
        return list(memory_keys)
    
    def stats(self) -> Dict[str, Any]:
        stats = {
            'memory': self.memory_cache.stats(),
            'redis_enabled': self.redis_enabled
        }
        
        if self.redis_enabled:
            # Add Redis connection info
            stats['redis'] = {
                'host': self.redis_cache.client.connection_pool.connection_kwargs.get('host'),
                'port': self.redis_cache.client.connection_pool.connection_kwargs.get('port'),
                'db': self.redis_cache.client.connection_pool.connection_kwargs.get('db')
            }
        
        return stats


# Global cache instance
_cache_instance: Optional[CacheBackend] = None


def get_cache() -> CacheBackend:
    """Get or create the global cache instance"""
    global _cache_instance
    
    if _cache_instance is None:
        # Default to memory cache
        _cache_instance = MemoryCache(max_size=1000, default_ttl=3600)
        logger.info("✅ Cache en memoria inicializado")
    
    return _cache_instance


def init_cache(backend: str = "memory", **kwargs) -> CacheBackend:
    """Initialize the global cache with specified backend"""
    global _cache_instance
    
    if backend == "memory":
        _cache_instance = MemoryCache(
            max_size=kwargs.get('max_size', 1000),
            default_ttl=kwargs.get('default_ttl', 3600)
        )
        logger.info(f"✅ Cache en memoria inicializado (max_size={kwargs.get('max_size', 1000)})")
    
    elif backend == "redis":
        if not REDIS_AVAILABLE:
            logger.warning("Redis no disponible. Usando cache en memoria.")
            return init_cache("memory", **kwargs)
        
        _cache_instance = RedisCache(
            host=kwargs.get('host', 'localhost'),
            port=kwargs.get('port', 6379),
            db=kwargs.get('db', 0),
            password=kwargs.get('password'),
            default_ttl=kwargs.get('default_ttl', 3600)
        )
        logger.info(f"✅ Cache Redis inicializado ({kwargs.get('host', 'localhost')}:{kwargs.get('port', 6379)})")
    
    elif backend == "hybrid":
        _cache_instance = HybridCache(
            memory_max_size=kwargs.get('memory_max_size', 1000),
            memory_ttl=kwargs.get('memory_ttl', 300),
            redis_host=kwargs.get('redis_host', 'localhost'),
            redis_port=kwargs.get('redis_port', 6379),
            redis_db=kwargs.get('redis_db', 0),
            redis_password=kwargs.get('redis_password'),
            redis_ttl=kwargs.get('redis_ttl', 3600)
        )
        logger.info("✅ Cache híbrido (memoria+Redis) inicializado")
    
    else:
        raise ValueError(f"Backend de cache no soportado: {backend}")
    
    return _cache_instance


# Utility functions for common caching patterns
def cache_key(*args, **kwargs) -> str:
    """Generate a cache key from function arguments"""
    key_parts = []
    
    # Add positional arguments
    for arg in args:
        if isinstance(arg, (str, int, float, bool, type(None))):
            key_parts.append(str(arg))
        else:
            # For complex objects, use hash
            key_parts.append(hashlib.md5(pickle.dumps(arg)).hexdigest()[:8])
    
    # Add keyword arguments
    for k, v in sorted(kwargs.items()):
        key_parts.append(f"{k}:{v}")
    
    return "::".join(key_parts)


def cached_function(ttl: int = 3600, key_prefix: str = ""):
    """Decorator for caching function results"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            cache = get_cache()
            
            # Generate cache key
            func_key = f"{key_prefix or func.__name__}:{cache_key(*args, **kwargs)}"
            
            # Try to get from cache
            cached_result = cache.get(func_key)
            if cached_result is not None:
                logger.debug(f"Cache hit para {func.__name__}")
                return cached_result
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Store in cache
            cache.set(func_key, result, ttl)
            logger.debug(f"Cache miss para {func.__name__}, almacenado con TTL {ttl}s")
            
            return result
        return wrapper
    return decorator


# Document cache wrapper for backward compatibility
class DocumentCache:
    """Wrapper for backward compatibility with existing code"""
    
    def __init__(self, max_size: int = 100, ttl: int = 3600):
        self.cache = MemoryCache(max_size=max_size, default_ttl=ttl)
        self.max_size = max_size
        self.ttl = ttl
    
    def __setitem__(self, key, value):
        self.cache.set(key, value, self.ttl)
    
    def __getitem__(self, key):
        value = self.cache.get(key)
        if value is None:
            raise KeyError(f"Key not found: {key}")
        return value
    
    def __contains__(self, key):
        return self.cache.exists(key)
    
    def __len__(self):
        return len(self.cache.cache)
    
    def keys(self):
        return self.cache.keys()
    
    def clear(self):
        return self.cache.clear()