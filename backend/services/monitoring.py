"""Health checks and monitoring for production."""
import logging
import psutil
import time
from datetime import datetime, timezone
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, func
from models.models import Product, Document, Category, Section

logger = logging.getLogger("monitoring")

class HealthMonitor:
    """Monitor application health state."""

    def __init__(self):
        self.start_time = time.time()

    async def get_full_health(self, db: AsyncSession) -> Dict[str, Any]:
        """Return full health check report."""
        try:
            return {
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "uptime_seconds": int(time.time() - self.start_time),
                "database": await self._check_database(db),
                "system": self._check_system(),
                "cache": await self._check_cache(db),
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def _check_database(self, db: AsyncSession) -> Dict[str, Any]:
        """Check database connection and collect stats."""
        try:
            # Connection test
            await db.execute(text("SELECT 1"))
            
            # Get statistics
            doc_count = await db.scalar(select(func.count(Document.id)))
            product_count = await db.scalar(select(func.count(Product.id)))
            category_count = await db.scalar(select(func.count(Category.id)))
            
            return {
                "connected": True,
                "documents": doc_count or 0,
                "products": product_count or 0,
                "categories": category_count or 0,
                "status": "ok"
            }
        except Exception as e:
            return {"connected": False, "error": str(e), "status": "error"}
    
    def _check_system(self) -> Dict[str, Any]:
        """Check system resource usage (non-blocking)."""
        return {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent,
            "status": "ok"
        }
    
    async def _check_cache(self, db: AsyncSession) -> Dict[str, Any]:
        """Check Redis cache availability."""
        try:
            # Try to connect to Redis if available
            import redis
            r = redis.Redis(host='redis', port=6379, decode_responses=True)
            r.ping()
            
            cache_size = len(r.keys('*'))
            return {
                "connected": True,
                "type": "redis",
                "keys": cache_size,
                "status": "ok"
            }
        except Exception as e:
            return {
                "connected": False,
                "type": "none",
                "error": str(e),
                "status": "warning"
            }

# Global instance
monitor = HealthMonitor()
