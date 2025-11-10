# app/tasks/analysis_tasks.py
import asyncio
from datetime import datetime

from app.models.debt import TechnicalDebt
from app.models.project import Project
from app.tasks.celery_app import celery_app
from app.core.database import SessionLocal
from app.services.analysis_orchestrator import AnalysisOrchestrator
from app.repositories.project_repository import ProjectRepository
from app.repositories.debt_repository import DebtRepository


@celery_app.task(bind=True)
def analyze_project_task(self, project_id: int, file_path: str = None):
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
        # 如果提供 file_path，则将其作为分析目标（orchestrator 可选择支持）
        target = project.local_path
        if file_path:
            target = file_path

        # 在 DB 中标记 task 正在运行（current_analysis_id/status）
        try:
            task_id = getattr(self.request, 'id', None) or getattr(self, 'id', None)
            if task_id:
                project.current_analysis_id = task_id
                project.status = 'analyzing'
                db.add(project)
                db.commit()
        except Exception:
            db.rollback()

        # 更新任务状态到 Celery meta
        try:
            self.update_state(state='STARTED', meta={'message': 'analysis started', 'started_at': None, 'progress': 0})
        except Exception:
            pass

        analysis_result = asyncio.run(orchestrator.analyze_project(target))

        # 保存债务项目并在每个文件后更新任务进度
        debt_scores = analysis_result.get('debt_scores', {})
        total = max(1, len(debt_scores))
        processed = 0
        for fpath, debt_data in debt_scores.items():
            debt_item = {
                'project_id': project_id,
                'file_path': fpath,
                'line': debt_data.get('line') if isinstance(debt_data, dict) else None,
                'debt_type': 'hotspot',
                'severity': debt_data.get('severity'),
                'description': f"Technical debt hotspot: {debt_data.get('debt_score', 0):.2f} score",
                'estimated_effort': debt_data.get('estimated_effort'),
                'metadata': debt_data
            }
            try:
                debt_repo.create(debt_item)
            except Exception:
                # don't fail whole task on single debt save error
                pass

            processed += 1
            # 更新 Celery 任务状态进度
            try:
                progress = int(processed / total * 100)
                self.update_state(state='PROGRESS', meta={'message': 'processing', 'progress': progress, 'processed': processed, 'total': total})
            except Exception:
                pass

        # 标记为完成并返回信息；更新项目表
        try:
            task_id = getattr(self.request, 'id', None) or getattr(self, 'id', None)
            project.current_analysis_id = None
            project.last_analysis_id = task_id
            project.last_analysis_at = datetime.now()
            project.status = 'idle'
            db.add(project)
            db.commit()
        except Exception:
            db.rollback()

        return {"status": "completed", "project_id": project_id, 'finished_at': datetime.now().isoformat()}

    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        db.close()
