# app/tasks/analysis_tasks.py
import asyncio

from app.models.debt import TechnicalDebt
from app.models.project import Project
from app.tasks.celery_app import celery_app
from app.core.database import SessionLocal
from app.services.analysis_orchestrator import AnalysisOrchestrator
from app.repositories.project_repository import ProjectRepository
from app.repositories.debt_repository import DebtRepository


@celery_app.task(bind=True)
def analyze_project_task(self, project_id: int):
    """异步分析项目任务"""
    db = SessionLocal()
    try:
        project_repo = ProjectRepository(Project, db)
        debt_repo = DebtRepository(TechnicalDebt, db)

        project = project_repo.get(project_id)
        if not project:
            return {"status": "error", "message": "Project not found"}

        # 执行分析
        orchestrator = AnalysisOrchestrator()
        analysis_result = asyncio.run(orchestrator.analyze_project(project.local_path))

        # 保存债务项目
        for file_path, debt_data in analysis_result['debt_scores'].items():
            debt_item = {
                'project_id': project_id,
                'file_path': file_path,
                'debt_type': 'hotspot',
                'severity': debt_data['severity'],
                'description': f"Technical debt hotspot: {debt_data['debt_score']:.2f} score",
                'estimated_effort': debt_data['estimated_effort'],
                'metadata': debt_data
            }
            debt_repo.create(debt_item)

        return {"status": "completed", "project_id": project_id}

    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        db.close()
