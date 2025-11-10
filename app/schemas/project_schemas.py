# app/schemas/project_schemas.py
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from pydantic import ConfigDict


def _to_camel(s: str) -> str:
    parts = s.split('_')
    return parts[0] + ''.join(p.title() for p in parts[1:])


class ProjectBase(BaseModel):
    """项目基础模式"""
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=255, description="项目名称")
    description: Optional[str] = Field(None, description="项目描述")
    repo_url: Optional[str] = Field(None, description="代码仓库URL")
    local_path: Optional[str] = Field(None, description="本地路径")
    language: Optional[str] = Field(None, description="主要编程语言")
    status: Optional[str] = Field(default="idle", description="项目状态")


class ProjectCreate(ProjectBase):
    """创建项目请求模式"""
    pass


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)

    """更新项目请求模式"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    repo_url: Optional[str] = None
    local_path: Optional[str] = None
    language: Optional[str] = None


class ProjectResponse(ProjectBase):
    """项目响应模式（返回 camelCase 别名）"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    locked_by: Optional[str] = None
    lock_expires_at: Optional[datetime] = None
    current_analysis_id: Optional[str] = None
    last_analysis_id: Optional[str] = None
    last_analysis_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
