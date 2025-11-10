# app/services/project_service.py
from typing import List, Optional, Dict
import uuid

from app.models.debt import TechnicalDebt
from app.models.project import Project
from app.repositories.project_repository import ProjectRepository
from app.repositories.debt_repository import DebtRepository
from app.services.analysis_orchestrator import AnalysisOrchestrator


class ProjectService:
    def __init__(self, db):
        self.project_repo = ProjectRepository(Project, db)
        self.debt_repo = DebtRepository(TechnicalDebt, db)
        self.analyzer = AnalysisOrchestrator()

    def create_project(self, project_data: dict) -> Project:
        """创建新项目"""
        project = self.project_repo.create(project_data)

        # 触发初始分析
        self.trigger_analysis(project.id)

        return project

    def trigger_analysis(self, project_id: int, file_path: str = None) -> str:
        """触发代码分析（异步）。

        流程：生成 task_id -> apply_async (指定 task_id) -> 在 DB 事务中写 current_analysis_id。
        如果 DB 写入失败，会尝试 revoke 刚刚入队的任务以避免 dangling task。
        """
        from app.tasks.analysis_tasks import analyze_project_task
        from sqlalchemy.exc import SQLAlchemyError
        session = self.project_repo.db

        task_id = str(uuid.uuid4())
        try:
            task = analyze_project_task.apply_async(args=(project_id, file_path), task_id=task_id)
        except Exception as e:
            msg = str(e)
            try:
                import redis as _redis
                if isinstance(e, _redis.exceptions.RedisError) or 'redis' in msg.lower() or 'broker' in msg.lower():
                    raise RuntimeError(f"Cannot connect to Redis broker: {msg}")
            except Exception:
                raise RuntimeError(f"Failed to enqueue analysis task: {msg}")

        # 若发送成功，写入 DB（行级锁以避免并发）
        try:
            with session.begin():
                project = session.query(Project).with_for_update().filter(Project.id == project_id).first()
                if not project:
                    # 未找到项目，撤销任务
                    try:
                        from app.tasks.celery_app import celery_app
                        celery_app.control.revoke(task_id, terminate=False)
                    except Exception:
                        pass
                    raise RuntimeError('project_not_found')

                if project.current_analysis_id and project.status == 'analyzing':
                    # 已有在跑的分析，撤销刚刚创建的任务
                    try:
                        from app.tasks.celery_app import celery_app
                        celery_app.control.revoke(task_id, terminate=False)
                    except Exception:
                        pass
                    raise RuntimeError('already_analyzing')

                project.current_analysis_id = task_id
                project.status = 'queued'
                session.add(project)
            return task_id
        except Exception:
            # 如果 DB 写入失败，尝试撤销任务以避免 dangling task
            try:
                from app.tasks.celery_app import celery_app
                celery_app.control.revoke(task_id, terminate=False)
            except Exception:
                pass
            # 将错误上抛，API 层会映射为 503/400/409 等
            raise

    def get_project_debt_summary(self, project_id: int) -> Dict:
        """获取项目债务摘要"""
        debts = self.debt_repo.get_by_project(project_id)

        summary = {
            'total_debts': len(debts),
            'by_severity': {},
            'total_estimated_effort': 0
        }

        for debt in debts:
            severity = debt.severity
            summary['by_severity'][severity] = summary['by_severity'].get(severity, 0) + 1
            est = getattr(debt, 'estimated_effort', 0) or 0
            summary['total_estimated_effort'] += est

        return summary