# app/repositories/project_repository.py
from typing import Optional, List, Type
import os

from app.models.project import Project
from app.repositories.base import BaseRepository
from sqlalchemy import func


def _normalize_path(p: str) -> Optional[str]:
    if not p:
        return p
    # Normalise OS path semantics, replace backslashes with forward slashes and strip trailing slashes
    p = os.path.normpath(p)
    p = p.replace('\\', '/').rstrip('/')
    # On Windows, comparisons should be case-insensitive
    if os.name == 'nt':
        p = p.lower()
    return p


class ProjectRepository(BaseRepository[Project]):
    def get_by_name(self, name: str) -> list[Project]:
        return self.db.query(Project).filter(Project.name == name).first()

    def get_by_local_path(self, local_path: str):
        """查找时对路径做归一化：normpath, 替换反斜杠, 去尾斜杠, Windows 下忽略大小写"""
        norm = _normalize_path(local_path)
        if norm is None:
            return None

        # Compare normalized values; for portability we lower both sides on Windows
        if os.name == 'nt':
            # Use SQL lower() for DB side lowercasing and trim trailing slashes
            db_expr = func.lower(func.rtrim(func.replace(Project.local_path, '\\', '/'), '/'))
            return self.db.query(Project).filter(db_expr == norm).first()
        else:
            db_expr = func.rtrim(func.replace(Project.local_path, '\\', '/'), '/')
            return self.db.query(Project).filter(db_expr == norm).first()

    def list_active(self) -> list[Type[Project]]:
        return self.db.query(Project).all()