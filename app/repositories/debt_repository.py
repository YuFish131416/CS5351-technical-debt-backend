# app/repositories/debt_repository.py
from app.models.debt import TechnicalDebt
from sqlalchemy import and_

from app.repositories.base import BaseRepository


class DebtRepository(BaseRepository[TechnicalDebt]):
    def get_by_project(self, project_id: int) -> List[TechnicalDebt]:
        return self.db.query(TechnicalDebt).filter(
            TechnicalDebt.project_id == project_id
        ).all()

    def get_critical_debts(self, project_id: int) -> List[TechnicalDebt]:
        return self.db.query(TechnicalDebt).filter(
            and_(
                TechnicalDebt.project_id == project_id,
                TechnicalDebt.severity.in_(['high', 'critical'])
            )
        ).all()