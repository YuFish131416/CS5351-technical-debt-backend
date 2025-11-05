# app/schemas/project_schemas.py
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class ProjectBase(BaseModel):
    """项目基础模式"""
    name: str = Field(..., min_length=1, max_length=255, description="项目名称")
    description: Optional[str] = Field(None, description="项目描述")
    repo_url: Optional[str] = Field(None, description="代码仓库URL")
    local_path: Optional[str] = Field(None, description="本地路径")
    language: Optional[str] = Field(None, description="主要编程语言")


class ProjectCreate(ProjectBase):
    """创建项目请求模式"""
    pass


class ProjectUpdate(BaseModel):
    """更新项目请求模式"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    repo_url: Optional[str] = None
    local_path: Optional[str] = None
    language: Optional[str] = None


class ProjectResponse(ProjectBase):
    """项目响应模式"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
