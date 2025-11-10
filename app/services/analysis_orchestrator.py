import asyncio
from typing import Dict, Optional
from datetime import datetime
import os

from app.analysis.code_analyzer import CodeComplexityAnalyzer
from app.analysis.debt_calculator import TechnicalDebtCalculator
from app.analysis.git_analyzer import GitHistoryAnalyzer


class AnalysisOrchestrator:
    """分析协调器"""

    def __init__(self):
        self.git_analyzer = GitHistoryAnalyzer()
        self.complexity_analyzer = CodeComplexityAnalyzer()
        self.debt_calculator = TechnicalDebtCalculator()

    async def analyze_project(self, project_path: str, file_path: Optional[str] = None) -> Dict:
        """执行完整项目分析。可选传入 file_path 以仅分析单个文件。"""
        target = file_path if file_path else project_path

        # 并行执行不同分析（对于单文件分析，git 分析器或许返回 limited data）
        git_task = asyncio.create_task(self.git_analyzer.analyze(target))
        complexity_task = asyncio.create_task(self.complexity_analyzer.analyze(target))

        git_data, complexity_data = await asyncio.gather(git_task, complexity_task)

        # 计算债务分数
        debt_scores = self.debt_calculator.calculate_debt_score(git_data, complexity_data)

        return {
            'git_analysis': git_data,
            'complexity_analysis': complexity_data,
            'debt_scores': debt_scores,
            'timestamp': datetime.now().isoformat()
        }