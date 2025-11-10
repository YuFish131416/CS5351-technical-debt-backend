# app/api/debts.py
from fastapi import APIRouter, HTTPException
from fastapi.params import Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import os

from app.core.database import get_db
from app.models.debt import TechnicalDebt
from sqlalchemy import func

debt_router = APIRouter(prefix="/debts", tags=["debts"])


def _normalize_path(p: str) -> Optional[str]:
    if not p:
        return p
    p = os.path.normpath(p)
    p = p.replace('\\', '/').rstrip('/')
    if os.name == 'nt':
        p = p.lower()
    return p


@debt_router.get("/project/{project_id}")
def get_project_debts(project_id: int, file_path: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """返回项目债务列表，支持可选的 file_path 查询参数。返回标准化 debt 对象数组（可能为空）。

    Incoming `file_path` will be normalized (normpath, backslashes -> '/', strip trailing slash).
    Comparison is done against a normalized DB expression to improve Windows compatibility.
    """
    from app.repositories.debt_repository import DebtRepository
    try:
        repo = DebtRepository(TechnicalDebt, db)
        query = db.query(TechnicalDebt).filter(TechnicalDebt.project_id == project_id)
        if file_path:
            norm = _normalize_path(file_path)
            if os.name == 'nt':
                db_expr = func.lower(func.rtrim(func.replace(TechnicalDebt.file_path, '\\', '/'), '/'))
                query = query.filter(db_expr == norm)
            else:
                db_expr = func.rtrim(func.replace(TechnicalDebt.file_path, '\\', '/'), '/')
                query = query.filter(db_expr == norm)

        debts = query.all()

        results = []
        for d in debts:
            results.append({
                "id": d.id,
                "file_path": d.file_path,
                # 'line' may not be available in current model; provide None if missing
                "line": getattr(d, 'line', None),
                "severity": d.severity,
                "message": d.description,
                "status": d.status,
                "created_at": d.created_at.isoformat() if getattr(d, 'created_at', None) else None,
                "updated_at": d.updated_at.isoformat() if getattr(d, 'updated_at', None) else None
            })
        return results
    except Exception as e:
        # Treat dependency/db errors as 503
        raise HTTPException(status_code=503, detail={"error": "dependency_unavailable", "service": "db", "message": str(e)})


@debt_router.put("/{debt_id}")
def update_debt_status(debt_id: int, payload: dict, db: Session = Depends(get_db)):
    """更新债务状态：{ "status": "in_progress" }等，返回更新后的 debt 对象或错误码"""
    from app.repositories.debt_repository import DebtRepository
    valid_statuses = {"open", "in_progress", "resolved", "ignored"}
    status_val = payload.get("status")
    if not status_val or status_val not in valid_statuses:
        raise HTTPException(status_code=400, detail={"error": "invalid_status", "message": "Invalid status value"})

    try:
        repo = DebtRepository(TechnicalDebt, db)
        debt = repo.get(debt_id)
        if not debt:
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Debt not found"})

        updated = repo.update(debt_id, {"status": status_val})
        return {
            "id": updated.id,
            "file_path": updated.file_path,
            "line": getattr(updated, 'line', None),
            "severity": updated.severity,
            "message": updated.description,
            "status": updated.status,
            "created_at": updated.created_at.isoformat() if getattr(updated, 'created_at', None) else None,
            "updated_at": updated.updated_at.isoformat() if getattr(updated, 'updated_at', None) else None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail={"error": "dependency_unavailable", "service": "db", "message": str(e)})