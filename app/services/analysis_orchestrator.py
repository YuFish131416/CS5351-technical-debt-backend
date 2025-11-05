import asyncio
from typing import Dict

from app.analysis.code_analyzer import CodeComplexityAnalyzer
from app.analysis.debt_calculator import TechnicalDebtCalculator
from app.analysis.git_analyzer import GitHistoryAnalyzer


class AnalysisOrchestrator:
    """分析协调器"""

    def __init__(self):
        self.git_analyzer = GitHistoryAnalyzer()
        self.complexity_analyzer = CodeComplexityAnalyzer()
        self.debt_calculator = TechnicalDebtCalculator()

    async def analyze_project(self, project_path: str) -> Dict:
        """执行完整项目分析"""
        # 并行执行不同分析
        git_task = asyncio.create_task(self.git_analyzer.analyze(project_path))
        complexity_task = asyncio.create_task(self.complexity_analyzer.analyze(project_path))

        git_data, complexity_data = await asyncio.gather(git_task, complexity_task)

        # 计算债务分数
        debt_scores = self.debt_calculator.calculate_debt_score(git_data, complexity_data)

        return {
            'git_analysis': git_data,
            'complexity_analysis': complexity_data,
            'debt_scores': debt_scores,
            'timestamp': datetime.now().isoformat()
        }