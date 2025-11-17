# app/api/debts.py
import asyncio
import json
import logging
import os
import traceback
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.params import Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.debt import TechnicalDebt
from app.models.project import Project
from app.repositories.debt_repository import DebtRepository
from app.repositories.project_repository import ProjectRepository
from app.services.analysis_orchestrator import AnalysisOrchestrator
from app.tasks.analysis_tasks import _serialize_metadata, _write_scan_log

debt_router = APIRouter(prefix="/debts", tags=["debts"])
logger = logging.getLogger(__name__)


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
    try:
        if file_path:
            _run_inline_analysis(db, project_id, file_path)

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
            metadata = _load_metadata(d.project_metadata)
            results.append({
                "id": d.id,
                "file_path": d.file_path,
                # 'line' may not be available in current model; provide None if missing
                "line": getattr(d, 'line', None),
                "severity": d.severity,
                "message": d.description,
                "status": d.status,
                "metadata": metadata,
                "created_at": d.created_at.isoformat() if getattr(d, 'created_at', None) else None,
                "updated_at": d.updated_at.isoformat() if getattr(d, 'updated_at', None) else None
            })
        return results
    except HTTPException:
        raise
    except Exception as e:
        # Treat dependency/db errors as 503
        raise HTTPException(status_code=503, detail={"error": "dependency_unavailable", "service": "db", "message": str(e)})


@debt_router.put("/{debt_id}")
def update_debt_status(debt_id: int, payload: dict, db: Session = Depends(get_db)):
    """更新债务状态：{ "status": "in_progress" }等，返回更新后的 debt 对象或错误码"""
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
        metadata = _load_metadata(updated.project_metadata)
        return {
            "id": updated.id,
            "file_path": updated.file_path,
            "line": getattr(updated, 'line', None),
            "severity": updated.severity,
            "message": updated.description,
            "status": updated.status,
            "metadata": metadata,
            "created_at": updated.created_at.isoformat() if getattr(updated, 'created_at', None) else None,
            "updated_at": updated.updated_at.isoformat() if getattr(updated, 'updated_at', None) else None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail={"error": "dependency_unavailable", "service": "db", "message": str(e)})


def _run_inline_analysis(db: Session, project_id: int, incoming_path: str):
    project_repo = ProjectRepository(Project, db)
    project = project_repo.get(project_id)
    if not project:
        detail = {"error": "project_not_found", "message": "Project not found"}
        _log_analysis_error(project_id, incoming_path, detail)
        logger.error("Inline analysis aborted: project %s not found for file %s", project_id, incoming_path)
        raise HTTPException(status_code=404, detail=detail)

    try:
        resolved_file = _resolve_target_path(project, incoming_path)
    except HTTPException as exc:
        if exc.status_code == 404 and _is_virtual_path(incoming_path):
            detail = {"info": "virtual_path_skipped", "message": "Virtual document was ignored"}
            _log_analysis_error(project_id, incoming_path, detail)
            logger.info("Skipping inline analysis for virtual path project=%s path=%s", project_id, incoming_path)
            return
        raise

    orchestrator = AnalysisOrchestrator()
    try:
        analysis_result = asyncio.run(
            orchestrator.analyze_project(project.local_path or resolved_file, file_path=resolved_file)
        )
    except HTTPException as http_exc:
        if http_exc.status_code == 404 and _is_virtual_path(incoming_path):
            detail = {"info": "virtual_path_skipped", "message": "Virtual document was ignored"}
            _log_analysis_error(project_id, incoming_path, detail)
            logger.info("Skipping inline analysis for virtual path project=%s path=%s", project_id, incoming_path)
            return
        _log_analysis_error(project_id, resolved_file, http_exc.detail)
        logger.warning("Inline analysis raised HTTPException for project=%s file=%s detail=%s", project_id, resolved_file, http_exc.detail)
        raise
    except FileNotFoundError:
        detail = {"error": "file_not_found", "message": "File not found"}
        _log_analysis_error(project_id, resolved_file, detail)
        logger.error("Inline analysis failed: file missing project=%s file=%s", project_id, resolved_file)
        raise HTTPException(status_code=404, detail=detail)
    except Exception as exc:
        message = str(exc) or repr(exc)
        detail = {"error": "analysis_failed", "message": message}
        _log_analysis_error(project_id, resolved_file, detail, exc)
        logger.exception("Inline analysis error for project=%s file=%s", project_id, resolved_file)
        raise HTTPException(status_code=500, detail=detail)

    debt_scores = analysis_result.get('debt_scores', {}) or {}
    if not debt_scores:
        detail = {"info": "analysis_completed", "message": "No debt scores produced"}
        _log_analysis_error(project_id, resolved_file, detail)
        logger.info("Inline analysis produced no scores project=%s file=%s", project_id, resolved_file)
        return

    persisted = _persist_debt_scores(db, project_id, debt_scores)
    if persisted:
        _write_scan_log(project_id, persisted)


def _resolve_target_path(project: Project, incoming_path: str) -> str:
    if not incoming_path:
        detail = {"error": "invalid_path", "message": "File path is required"}
        _log_analysis_error(project.id if project else None, incoming_path, detail)
        logger.error("Inline analysis missing file_path for project=%s", project.id if project else None)
        raise HTTPException(status_code=400, detail=detail)

    candidates = []
    try:
        candidates.append(Path(incoming_path).expanduser())
    except Exception:
        pass

    if project and project.local_path:
        try:
            base = Path(project.local_path)
            candidates.append(base / incoming_path)
        except Exception:
            pass

    for candidate in candidates:
        if not candidate:
            continue
        try:
            if candidate.exists():
                return str(candidate.resolve())
        except Exception:
            continue

    if project and project.local_path:
        root = Path(project.local_path).resolve()
        relative_candidates = _build_relative_candidates(root, incoming_path)
        for rel in relative_candidates:
            matched = _case_insensitive_lookup(root, rel)
            if matched:
                return str(matched.resolve())

    detail = {"error": "file_not_found", "message": "Could not locate requested file on disk"}
    _log_analysis_error(project.id if project else None, incoming_path, detail)
    logger.error("Inline analysis could not resolve file for project=%s path=%s", project.id if project else None, incoming_path)
    raise HTTPException(status_code=404, detail=detail)


def _is_virtual_path(path: str | None) -> bool:
    if not path:
        return False
    lowered = path.lower()
    if lowered.startswith('extension-output-'):
        return True
    if lowered.startswith('vscode-remote://') or lowered.startswith('vscode-userdata://'):
        return True
    if lowered.startswith('untitled:'):
        return True
    return False


def _build_relative_candidates(root: Path, incoming_path: str) -> List[str]:
    candidates: List[str] = []
    normalized_incoming = str(incoming_path).replace('\\', '/').strip()

    if not normalized_incoming:
        return candidates

    incoming_path_obj = Path(normalized_incoming)
    if not incoming_path_obj.is_absolute():
        candidates.append(normalized_incoming)
    else:
        lower_root = str(root).lower().rstrip('/\\')
        lower_incoming = str(incoming_path_obj).lower()
        if lower_incoming.startswith(lower_root):
            rel = lower_incoming[len(lower_root):].lstrip('/\\')
            if rel:
                candidates.append(rel)

    parts = normalized_incoming.split('/')
    if parts:
        stripped = '/'.join(part for part in parts if part not in {'', '.'})
        if stripped and stripped not in candidates:
            candidates.append(stripped)

    return candidates


def _case_insensitive_lookup(root: Path, relative_path: str) -> Optional[Path]:
    current = root
    for part in Path(relative_path).parts:
        if part in {'.', ''}:
            continue
        try:
            entries = list(current.iterdir())
        except FileNotFoundError:
            return None
        lowered_map = {entry.name.lower(): entry for entry in entries}
        target = part.lower()
        match = lowered_map.get(target)
        if not match:
            stripped_target = target.lstrip('_')
            for entry in entries:
                if entry.name.lower().lstrip('_') == stripped_target:
                    match = entry
                    break
        if not match:
            return None
        current = match
    return current if current.exists() else None


def _log_analysis_error(project_id: Optional[int], file_path: Optional[str], detail: Dict, exc: Exception | None = None):
    try:
        normalized_path = _normalize_storage_path(file_path) if file_path else (file_path or '')
    except Exception:
        normalized_path = file_path or ''

    severity = 'error'
    if detail and 'error' not in detail and detail.get('info'):
        severity = 'info'

    metadata = {'detail': detail or {}}
    if exc is not None:
        metadata['exception'] = str(exc) or repr(exc)
        metadata['exception_type'] = exc.__class__.__name__
        metadata['traceback'] = ''.join(traceback.format_exception(exc.__class__, exc, exc.__traceback__))

    entry = [{
        'file_path': normalized_path,
        'debt_score': 0.0,
        'severity': severity,
        'metadata': metadata,
    }]

    try:
        _write_scan_log(project_id if project_id is not None else -1, entry)
    except Exception:
        logger.exception("Failed to write analysis error log for project=%s file=%s", project_id, file_path)


def _persist_debt_scores(db: Session, project_id: int, debt_scores: Dict) -> List[Dict]:
    persisted: List[Dict] = []

    for raw_path, debt_data in debt_scores.items():
        stored_path = _choose_storage_path(raw_path, debt_data)
        normalized_lookup = _normalize_path(stored_path)

        query = db.query(TechnicalDebt).filter(TechnicalDebt.project_id == project_id)
        if normalized_lookup:
            db_expr = func.lower(func.rtrim(func.replace(TechnicalDebt.file_path, '\\', '/'), '/'))
            query = query.filter(db_expr == normalized_lookup)
        else:
            query = query.filter(TechnicalDebt.file_path == stored_path)

        description = f"Technical debt hotspot: {debt_data.get('debt_score', 0.0):.2f} score"
        metadata_json = _serialize_metadata(debt_data)
        existing = query.first()

        if existing:
            existing.file_path = stored_path
            existing.line = debt_data.get('line')
            existing.debt_type = 'hotspot'
            existing.severity = debt_data.get('severity', 'low')
            existing.description = description
            existing.estimated_effort = debt_data.get('estimated_effort')
            existing.project_metadata = metadata_json
        else:
            new_debt = TechnicalDebt(
                project_id=project_id,
                file_path=stored_path,
                line=debt_data.get('line'),
                debt_type='hotspot',
                severity=debt_data.get('severity', 'low'),
                description=description,
                estimated_effort=debt_data.get('estimated_effort'),
                project_metadata=metadata_json,
            )
            db.add(new_debt)

        persisted.append({
            'file_path': stored_path,
            'debt_score': debt_data.get('debt_score', 0.0),
            'severity': debt_data.get('severity', 'low'),
            'metadata': debt_data,
        })

    db.commit()
    return persisted


def _load_metadata(raw_value: Optional[str]):
    if not raw_value:
        return None
    try:
        return json.loads(raw_value)
    except (TypeError, ValueError):
        logger.warning("Failed to parse technical debt metadata")
        return None


def _choose_storage_path(raw_key: str, debt_data: Dict) -> str:
    candidates = [
        (debt_data.get('complexity_metrics') or {}).get('relative_path'),
        raw_key,
        (debt_data.get('complexity_metrics') or {}).get('absolute_path'),
    ]

    for candidate in candidates:
        if candidate:
            normalized = _normalize_storage_path(candidate)
            if normalized:
                return normalized

    return _normalize_storage_path(raw_key)


def _normalize_storage_path(value: str) -> str:
    if not value:
        return ''
    normalized = str(value).replace('\\', '/').rstrip('/')
    if os.name == 'nt':
        normalized = normalized.lower()
    return normalized