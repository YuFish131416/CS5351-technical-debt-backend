# app/models/project.py
from sqlalchemy import Column, String, Text, JSON, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.analysis import CodeAnalysis
from app.models.base import BaseModel


class Project(BaseModel):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint('local_path', name='uq_projects_local_path'),
    )

    name = Column(String(255), nullable=False)
    description = Column(Text)
    repo_url = Column(String(500))
    local_path = Column(String(500))
    language = Column(String(50))

    # Status and analysis tracking fields
    # NOTE: manual lock fields (locked_by, lock_expires_at) were removed
    # as locking is handled automatically by the analysis task.
    status = Column(String(50), default='idle')
    current_analysis_id = Column(String(100), nullable=True)
    last_analysis_id = Column(String(100), nullable=True)
    last_analysis_at = Column(DateTime(timezone=True), nullable=True)

    # 关系
    analyses = relationship("CodeAnalysis", back_populates="project")
    debt_items = relationship("TechnicalDebt", back_populates="project")