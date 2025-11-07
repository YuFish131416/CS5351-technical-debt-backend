# app/models/debt.py
from sqlalchemy import Integer, ForeignKey, String, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.testing.schema import Column

from app.models.base import BaseModel


class TechnicalDebt(BaseModel):
    __tablename__ = "technical_debts"

    project_id = Column(Integer, ForeignKey("projects.id"))
    file_path = Column(String(500))
    debt_type = Column(String(50))  # 'complexity', 'duplication', 'smell', 'todo'
    severity = Column(String(20))  # 'low', 'medium', 'high', 'critical'
    description = Column(Text)
    estimated_effort = Column(Integer)  # 估算工时（小时）
    status = Column(String(20), default='open')  # 'open', 'in_progress', 'resolved'
    project_metadata = Column(String)  # 额外元数据

    project = relationship("Project", back_populates="debt_items")