"""
Servicio de caché con fallback a memoria
Redis opcional, lazy init
"""
import logging
import json
from typing import Optional, Any, Dict
from datetime import datetime, timedelta
import threading
import time

from config import settings
from database import redis_client

logger = logging.getLogger(__name__)


class MemoryCache:
    """Cache en memoria simple con TTL"""

    def __init__(self):
        self._cache:  Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """Obtener valor del cache"""
        with self._lock:
            entry = self._cache.get(key)
            if entry: 
                if entry.get('expires_at', 0) >= time.time():
                    return entry. get('value')
                else: 
                    del self._cache[key]
            return None

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """Establecer valor en cache"""
        with self._lock:
            self._cache[key] = {
                'value': value,
                'expires_at': time.time() + ttl
            }
        return True

    def delete(self, key: str) -> bool:
        """Eliminar valor del cache"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> bool:
        """Limpiar cache"""
        with self._lock:
            self._cache.clear()
        return True

    def get_stats(self) -> Dict[str, Any]:
        """Obtener estadísticas"""
        with self._lock:
            now = time.time()
            active = sum(1 for e in self._cache.values() if e.get('expires_at', 0) >= now)
            return {
                'total_entries': len(self._cache),
                'active_entries': active,
                'type': 'memory'
            }


class CacheService:
    """Servicio de caché unificado con fallback"""

    def __init__(self):
        self. redis_available = redis_client is not None
        self. memory_cache = MemoryCache()
        logger.info(f"CacheService inicializado.  Redis:  {self.redis_available}")

    def initialize(self):
        """Inicializar servicio"""
        logger.info("Cache service initialized")

    def is_connected(self) -> bool:
        """Verificar conexión a Redis"""
        if self.redis_available:
            try:
                redis_client.ping()
                return True
            except:
                return False
        return False

    def get_json(self, key: str) -> Optional[Any]:
        """Obtener JSON del cache"""
        try:
            if self.redis_available and redis_client:
                value = redis_client.get(key)
                if value:
                    return json.loads(value)
        except:
            pass

        return self.memory_cache.get(key)

    def set_json(self, key: str, value:  Any, ttl: int = 300) -> bool:
        """Establecer JSON en cache"""
        try:
            if self. redis_available and redis_client: 
                redis_client.setex(key, ttl, json. dumps(value))
        except:
            pass

        return self.memory_cache.set(key, value, ttl)

    def get_stats(self) -> Dict[str, Any]:
        """Obtener estadísticas"""
        return self.memory_cache.get_stats()

    def close(self):
        """Cerrar conexiones"""
        if self.redis_available and redis_client:
            try:
                redis_client.close()
            except:
                pass


# Instancia global
cache_service = CacheService()