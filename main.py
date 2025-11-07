# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.api import api_router
from app.api.projects import project_router  # 添加导入
from app.api.debts import debt_router        # 添加导入

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="A technical debt management tool for software projects"
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(api_router, prefix="/api/v1")
app.include_router(project_router, prefix="/api/v1")  # 添加项目路由
app.include_router(debt_router, prefix="/api/v1")        # 添加债务路由

@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    # 创建数据库表
    from app.core.database import engine, Base
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
