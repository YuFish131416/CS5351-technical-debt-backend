# app/schemas/debt_schemas.py
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class TechnicalDebtBase(BaseModel):
    """技术债务基础模式"""
    project_id: int
    file_path: str = Field(..., description="文件路径")
    debt_type: str = Field(..., description="债务类型")
    severity: str = Field(..., description="严重程度")
    description: str = Field(..., description="债务描述")
    estimated_effort: int = Field(..., ge=0, description="估算工时")
    status: str = Field(default="open", description="状态")


class TechnicalDebtCreate(TechnicalDebtBase):
    """创建技术债务请求模式"""
    metadata: Optional[Dict[str, Any]] = None


class TechnicalDebtUpdate(BaseModel):
    """更新技术债务请求模式"""
    severity: Optional[str] = None
    description: Optional[str] = None
    estimated_effort: Optional[int] = Field(None, ge=0)
    status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class TechnicalDebtResponse(TechnicalDebtBase):
    """技术债务响应模式"""
    id: int
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        