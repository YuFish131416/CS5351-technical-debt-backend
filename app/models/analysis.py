# app/models/analysis.py
from sqlalchemy import Integer, ForeignKey, String, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.testing.schema import Column

from app.models.base import BaseModel


class CodeAnalysis(BaseModel):
    __tablename__ = "code_analyses"

    project_id = Column(Integer, ForeignKey("projects.id"))
    analysis_type = Column(String(50))  # 'full', 'incremental'
    status = Column(String(20))  # 'pending', 'running', 'completed', 'failed'
    metrics = Column(JSON)  # 存储分析指标

    project = relationship("Project", back_populates="analyses")