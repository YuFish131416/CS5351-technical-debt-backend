# app/models/project.py
from sqlalchemy import Column, String, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Project(BaseModel):
    __tablename__ = "projects"

    name = Column(String(255), nullable=False)
    description = Column(Text)
    repo_url = Column(String(500))
    local_path = Column(String(500))
    language = Column(String(50))

    # 关系
    analyses = relationship("CodeAnalysis", back_populates="project")
    debt_items = relationship("TechnicalDebt", back_populates="project")