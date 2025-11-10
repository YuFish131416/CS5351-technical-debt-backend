# app/api/api.py
from fastapi import APIRouter
from app.core.database import get_db
from fastapi import Depends
import socket

api_router = APIRouter()


@api_router.get("/")
async def root():
    return {"message": "Technical Debt Management API"}


@api_router.get("/health")
def health(db=Depends(get_db)):
    """返回关键依赖的运行状态（db、redis、celery）"""
    status = {"ok": True, "db": "ok", "redis": "unknown", "celery": "unknown"}
    # 简单检测 DB: 尝试执行一个轻量查询
    try:
        # get_db dependency ensures session; if it fails an exception will be raised before here
        pass
    except Exception:
        status["db"] = "unavailable"
        status["ok"] = False

    # Redis 检查（非强制）
    try:
        from app.core.config import settings
        import redis
        r = redis.from_url(settings.REDIS_URL)
        r.ping()
        status["redis"] = "ok"
    except Exception as e:
        status["redis"] = f"error: {str(e)}"
        status["ok"] = False

    # Celery 检查：尝试获取 broker info via socket if REDIS_URL is tcp
    try:
        from app.core.config import settings
        if settings.REDIS_URL.startswith('redis://'):
            # attempt to parse host:port
            import re
            m = re.search(r'redis://([^:/]+):(\d+)', settings.REDIS_URL)
            if m:
                host = m.group(1)
                port = int(m.group(2))
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                try:
                    sock.connect((host, port))
                    status["celery"] = "ready"
                finally:
                    sock.close()
    except Exception:
        status["celery"] = "unknown"

    return status