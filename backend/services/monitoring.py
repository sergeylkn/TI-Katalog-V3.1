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
    """监控应用健康状态."""
    
    def __init__(self):
        self.start_time = time.time()
    
    async def get_full_health(self, db: AsyncSession) -> Dict[str, Any]:
        """获取完整健康检查报告."""
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
        """检查数据库连接和统计."""
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
        """检查系统资源使用情况."""
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent,
            "status": "ok"
        }
    
    async def _check_cache(self, db: AsyncSession) -> Dict[str, Any]:
        """检查缓存状态."""
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
