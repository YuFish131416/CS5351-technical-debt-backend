# app/api/debts.py
from fastapi import APIRouter
from fastapi.params import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.debt import TechnicalDebt

debt_router = APIRouter(prefix="/debts", tags=["debts"])

@debt_router.get("/project/{project_id}")
def get_project_debts(project_id: int, db: Session = Depends(get_db)):
    from app.repositories.debt_repository import DebtRepository
    repo = DebtRepository(TechnicalDebt, db)
    return repo.get_by_project(project_id)