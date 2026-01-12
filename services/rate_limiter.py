"""
Rate limiting service using in-memory token bucket
Compatible with cache_service for potential Redis fallback
"""
import time
from typing import Dict, Tuple
from datetime import datetime, timedelta

class RateLimiter:
    """
    In-memory token bucket rate limiter per IP address.
    Uses TTL to clean up old entries.
    """
    
    def __init__(self, rate: int = 100, per_seconds: int = 60, cleanup_interval: int = 300):
        """
        Args:
            rate: Number of requests allowed
            per_seconds: Per this many seconds
            cleanup_interval: Clean up old entries every N seconds
        """
        self.rate = rate
        self.per_seconds = per_seconds
        self.cleanup_interval = cleanup_interval
        
        # token_bucket[ip] = (tokens_remaining, last_refill_time, last_access_time)
        self.token_bucket: Dict[str, Tuple[float, float, float]] = {}
        self.last_cleanup = time.time()
    
    def is_allowed(self, ip: str) -> bool:
        """Check if request from IP is allowed under rate limit"""
        now = time.time()
        
        # Periodic cleanup
        if now - self.last_cleanup > self.cleanup_interval:
            self._cleanup_old_entries(now)
            self.last_cleanup = now
        
        # Get or initialize bucket
        if ip not in self.token_bucket:
            self.token_bucket[ip] = (self.rate, now, now)
        
        tokens, last_refill, last_access = self.token_bucket[ip]
        
        # Refill tokens based on elapsed time
        elapsed = now - last_refill
        tokens_to_add = (elapsed / self.per_seconds) * self.rate
        tokens = min(self.rate, tokens + tokens_to_add)
        
        # Check if request is allowed
        if tokens >= 1:
            tokens -= 1
            allowed = True
        else:
            allowed = False
        
        # Update bucket
        self.token_bucket[ip] = (tokens, now if tokens_to_add > 0 else last_refill, now)
        
        return allowed
    
    def _cleanup_old_entries(self, now: float, max_age: int = 3600):
        """Remove entries not accessed in max_age seconds"""
        keys_to_remove = [
            ip for ip, (_, _, last_access) in self.token_bucket.items()
            if now - last_access > max_age
        ]
        for ip in keys_to_remove:
            del self.token_bucket[ip]


# Global rate limiter instance
rate_limiter = RateLimiter(rate=100, per_seconds=60)
