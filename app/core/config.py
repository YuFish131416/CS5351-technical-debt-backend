# app/core/config.py
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用配置管理"""
    APP_NAME: str = "Technical Debt Manager"
    VERSION: str = "1.0.0"

    # 数据库配置
    DATABASE_URL: str
    TEST_DATABASE_URL: Optional[str] = None

    # Redis配置
    REDIS_URL: str

    # 安全配置
    SECRET_KEY: str
    ALGORITHM: str = "HS256"

    # 外部服务配置
    GITHUB_TOKEN: Optional[str] = None
    JIRA_URL: Optional[str] = None

    class Config:
        env_file = ".env"


settings = Settings()