# app/api/projects.py
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.schemas.project_schemas import ProjectCreate, ProjectResponse, ProjectUpdate
from app.schemas.analysis_schemas import AnalysisResponse
from app.services.project_service import ProjectService
from app.models.project import Project

project_router = APIRouter(prefix="/projects", tags=["projects"])

@project_router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    project: ProjectCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """创建新项目"""
    service = ProjectService(db)
    try:
        return service.create_project(project.dict())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"创建项目失败: {str(e)}"
        )

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
def trigger_analysis(project_id: int, db: Session = Depends(get_db)):
    """触发项目分析"""
    service = ProjectService(db)
    try:
        task_id = service.trigger_analysis(project_id)
        return {"task_id": task_id, "status": "started", "message": "分析任务已开始"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"触发分析失败: {str(e)}"
        )

@project_router.get("/{project_id}/debt-summary")
def get_debt_summary(project_id: int, db: Session = Depends(get_db)):
    """获取项目债务摘要"""
    service = ProjectService(db)
    try:
        return service.get_project_debt_summary(project_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"获取债务摘要失败: {str(e)}"
        )