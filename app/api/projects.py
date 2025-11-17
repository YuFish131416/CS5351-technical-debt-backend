# app/api/projects.py
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status, Body, Header, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.project_schemas import ProjectCreate, ProjectResponse, ProjectUpdate
from app.schemas.analysis_schemas import AnalysisResponse
from app.services.project_service import ProjectService
from app.services.analysis_orchestrator import AnalysisOrchestrator
from app.models.project import Project
from app.tasks.celery_app import celery_app
from app.api.debts import _persist_debt_scores
from app.tasks.analysis_tasks import _write_scan_log
import traceback
try:
    import redis as _redis
except Exception:
    _redis = None
from fastapi import Header, Request
from datetime import timedelta
from sqlalchemy.exc import SQLAlchemyError

project_router = APIRouter(prefix="/projects", tags=["projects"])


SUPPORTED_SUFFIXES = {
    '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.go', '.cpp', '.c', '.map', '.json', '.css', '.html'
}


def _is_supported_file(raw_path: str, debt_data: Dict) -> bool:
    metrics = debt_data.get('complexity_metrics') or {}
    language = metrics.get('language')
    if language:
        return True

    candidates = [
        metrics.get('absolute_path'),
        metrics.get('relative_path'),
        raw_path,
    ]

    for candidate in candidates:
        if not candidate:
            continue
        suffixes = [s.lower() for s in Path(str(candidate)).suffixes]
        if not suffixes:
            continue
        last = suffixes[-1]
        if last in SUPPORTED_SUFFIXES:
            return True
        if last == '.map' and len(suffixes) > 1 and suffixes[-2] in {'.js', '.ts'}:
            return True

    return False


@project_router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    project: ProjectCreate,
    background_tasks: BackgroundTasks,
    response: Response,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")
):
    """创建新项目。实现基于 localPath 的去重（方案 B），短期也可接收 Idempotency-Key header。

    行为：如果 local_path 已存在则返回 200 和已有项目；否则创建并返回 201。
    """
    from app.repositories.project_repository import ProjectRepository
    repo = ProjectRepository(Project, db)

    try:
        # 去重：先按 local_path 查找
        lp = project.local_path
        if lp:
            existing = repo.get_by_local_path(lp)
            if existing:
                # 返回 200 + existing
                response.status_code = status.HTTP_200_OK
                resp = {
                    "id": existing.id,
                    "project_id": existing.id,
                    "name": existing.name,
                    "localPath": existing.local_path,
                    "language": existing.language,
                    "status": existing.status,
                    "current_analysis_id": existing.current_analysis_id,
                    "currentAnalysisId": existing.current_analysis_id,
                    "created_at": existing.created_at.isoformat() if getattr(existing, 'created_at', None) else None
                }
                return resp

        # 否则创建
        proj = repo.create(project.dict())

        # 新建成功，保持 201
        resp = {
            "id": proj.id,
            "project_id": proj.id,
            "name": proj.name,
            "localPath": proj.local_path,
            "language": proj.language,
            "status": proj.status,
            "current_analysis_id": proj.current_analysis_id,
            "currentAnalysisId": proj.current_analysis_id,
            "created_at": proj.created_at.isoformat() if getattr(proj, 'created_at', None) else None
        }
        return resp

    except SQLAlchemyError as e:
        # 可能是 unique constraint 报错或 DB 问题
        msg = str(e)
        if 'unique' in msg.lower() or 'duplicate' in msg.lower():
            # 尝试返回已存在项（race condition）、用 local_path 再查一次
            try:
                existing = repo.get_by_local_path(project.local_path)
                if existing:
                    return {
                        "id": existing.id,
                        "project_id": existing.id,
                        "name": existing.name,
                        "localPath": existing.local_path,
                        "language": existing.language,
                        "status": existing.status,
                        "created_at": existing.created_at.isoformat() if getattr(existing, 'created_at', None) else None
                    }
            except Exception:
                pass
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error": "bad_request", "message": msg})
    except Exception as e:
        msg = str(e)
        if "redis" in msg.lower() or "broker" in msg.lower() or ( _redis is not None and isinstance(e, _redis.exceptions.RedisError) ) or "connection" in msg.lower():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "dependency_unavailable", "service": "redis", "message": msg}
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error": "bad_request", "message": msg})


@project_router.get("/by-path")
def get_project_by_path(localPath: str, db: Session = Depends(get_db)):
    """按 localPath 查询项目，返回 200 + project or 404"""
    from app.repositories.project_repository import ProjectRepository
    repo = ProjectRepository(Project, db)
    proj = repo.get_by_local_path(localPath)
    if not proj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return proj


# NOTE: Lock endpoints removed. Projects are now locked automatically during processing
# by the analysis task. Manual lock/renew/unlock endpoints were removed to avoid
# dual locking mechanisms. The task marks project.status/current_analysis_id at
# start and clears them on completion.


@project_router.get("/{project_id}/current")
def get_project_current(project_id: int, db: Session = Depends(get_db)):
    from app.repositories.project_repository import ProjectRepository
    repo = ProjectRepository(Project, db)
    project = repo.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Project not found"})
    if not project.local_path:
        raise HTTPException(status_code=400, detail={"error": "invalid_project", "message": "Project local path is missing"})

    project_root = Path(project.local_path).expanduser()
    if project_root.is_file():
        project_root = project_root.parent
    if not project_root.exists():
        raise HTTPException(status_code=404, detail={"error": "project_path_missing", "message": "Project local path does not exist"})

    orchestrator = AnalysisOrchestrator()
    try:
        analysis_result = asyncio.run(orchestrator.analyze_project(str(project_root)))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={"error": "project_path_missing", "message": "Project local path does not exist"})
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": "analysis_failed", "message": str(exc) or repr(exc)})

    debt_scores = analysis_result.get('debt_scores', {}) or {}
    filtered_scores: Dict[str, Dict] = {}
    for key, score_data in debt_scores.items():
        if _is_supported_file(key, score_data):
            filtered_scores[key] = score_data

    persisted = _persist_debt_scores(db, project.id, filtered_scores)
    if persisted:
        _write_scan_log(project.id, persisted)

    project.last_analysis_at = datetime.now(timezone.utc)
    project.status = 'idle'
    db.add(project)
    db.commit()
    db.refresh(project)

    return {
        "id": project.id,
        "current_analysis_id": project.current_analysis_id,
        "currentAnalysisId": project.current_analysis_id,
        "status": project.status
    }


@project_router.get("/", response_model=List[ProjectResponse])
def list_projects(
        skip: int = 0,
        limit: int = 100,
        db: Session = Depends(get_db)
):
    """获取项目列表"""
    from app.repositories.project_repository import ProjectRepository
    repo = ProjectRepository(Project, db)
    projects = repo.db.query(Project).offset(skip).limit(limit).all()
    return projects


@project_router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: int, db: Session = Depends(get_db)):
    """获取单个项目详情"""
    from app.repositories.project_repository import ProjectRepository
    repo = ProjectRepository(Project, db)
    project = repo.get(project_id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="项目不存在"
        )
    return project


@project_router.post("/{project_id}/analysis", status_code=status.HTTP_202_ACCEPTED)
def trigger_analysis(project_id: int, payload: dict = Body(default={}), db: Session = Depends(get_db)):
    """触发项目分析。接受可选 body {"file_path": "..."}，立即返回 analysis_id/status/message。"""
    service = ProjectService(db)
    try:
        file_path = payload.get("file_path") if isinstance(payload, dict) else None
        analysis_id = service.trigger_analysis(project_id, file_path=file_path)
        return {"analysis_id": analysis_id, "status": "pending", "message": "analysis queued"}
    except Exception as e:
        # 更语义化的错误映射
        msg = str(e)
        if 'already_analyzing' in msg:
            # 项目正在被分析/处理，返回统一的中文提示，便于前端展示友好信息
            # 使用 423 (Locked) 更清晰地表达资源被占用的语义
            code = getattr(status, 'HTTP_423_LOCKED', 423)
            raise HTTPException(status_code=code, detail={"error": "conflict", "message": "项目正在进行其他处理，请稍后操作"})
        if 'project_not_found' in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found", "message": "Project not found"})
        if "redis" in msg.lower() or "broker" in msg.lower():
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail={"error": "dependency_unavailable", "service": "redis", "message": msg})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error": "bad_request", "message": msg})


@project_router.get("/{project_id}/analysis/{analysis_id}")
def get_analysis_status(project_id: int, analysis_id: str):
    """查询分析任务状态（基于 Celery AsyncResult，如果可用）。"""
    from app.tasks.celery_app import celery_app
    try:
        async_result = celery_app.AsyncResult(analysis_id)
        state = async_result.state.lower() if async_result.state else "pending"
        # map celery states to desired states
        mapping = {
            'pending': 'pending',
            'received': 'pending',
            'started': 'running',
            'retry': 'running',
            'success': 'completed',
            'failure': 'failed'
        }
        status_val = mapping.get(state, state)
        info = async_result.info or {}
        response = {
            "analysis_id": analysis_id,
            "project_id": project_id,
            "status": status_val,
            "progress": info.get('progress') if isinstance(info, dict) else None,
            "message": info.get('message') if isinstance(info, dict) else None,
            "started_at": info.get('started_at') if isinstance(info, dict) else None,
            "finished_at": info.get('finished_at') if isinstance(info, dict) else None,
        }
        return response
    except Exception as e:
        # 如果是 broker/redis/连接相关的错误，返回 503 表示依赖不可用，便于前端重试或降级处理。
        msg = str(e)
        try:
            # _redis 在模块顶部尝试导入，若成功可用于类型检查
            if ( _redis is not None and hasattr(_redis, 'exceptions') and isinstance(e, _redis.exceptions.RedisError) ) or 'redis' in msg.lower() or 'broker' in msg.lower() or 'connection' in msg.lower():
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                    detail={"error": "dependency_unavailable", "service": "redis/celery", "message": msg})
        except Exception:
            # 报错时继续降级处理为 400
            pass

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error": "bad_request", "message": msg})


@project_router.get("/{project_id}/debt-summary")
def get_debt_summary(project_id: int, db: Session = Depends(get_db)):
    """获取项目债务摘要"""
    service = ProjectService(db)
    try:
        raw = service.get_project_debt_summary(project_id)
        # 标准化为前端期望的结构
        by_severity = raw.get('by_severity', {})
        # 汇总 by_status 目前服务端未维护，返回空字典或可从 debt repository 补充
        return {
            "project_id": project_id,
            "total": raw.get('total_debts', 0),
            "by_severity": by_severity,
            "by_status": {}
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"获取债务摘要失败: {str(e)}"
        )
