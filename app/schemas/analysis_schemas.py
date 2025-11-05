# app/schemas/analysis_schemas.py
from datetime import datetime
from typing import Optional, Dict, Any

from pydantic import BaseModel


class AnalysisBase(BaseModel):
    """分析基础模式"""
    analysis_type: str
    project_id: int


class AnalysisCreate(AnalysisBase):
    """创建分析请求模式"""
    pass


class AnalysisResponse(AnalysisBase):
    """分析响应模式"""
    id: int
    status: str
    metrics: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
