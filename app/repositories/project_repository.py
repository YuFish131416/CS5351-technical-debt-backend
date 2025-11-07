# app/repositories/project_repository.py
from typing import Optional, List, Type

from app.models.project import Project
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    def get_by_name(self, name: str) -> list[Project]:
        return self.db.query(Project).filter(Project.name == name).first()

    def list_active(self) -> list[Type[Project]]:
        return self.db.query(Project).all()