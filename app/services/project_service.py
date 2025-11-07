# app/services/project_service.py
from typing import List, Optional, Dict

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

    def trigger_analysis(self, project_id: int) -> str:
        """触发代码分析（异步）"""
        from app.tasks.analysis_tasks import analyze_project_task
        task = analyze_project_task.delay(project_id)
        return task.id

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
            summary['total_estimated_effort'] += debt.estimated_effort

        return summary