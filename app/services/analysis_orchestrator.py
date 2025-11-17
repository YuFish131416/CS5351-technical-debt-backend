import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

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
        if not project_path and not file_path:
            raise ValueError("project_path or file_path must be provided")

        git_target = project_path or file_path
        complexity_target = file_path or project_path

        resolved_project_root = None
        if project_path:
            resolved_project_root = project_path
        elif file_path:
            try:
                resolved_project_root = str(Path(file_path).resolve().parent)
            except Exception:
                resolved_project_root = None

        git_task = asyncio.create_task(self.git_analyzer.analyze(git_target))
        complexity_task = asyncio.create_task(
            self.complexity_analyzer.analyze(
                complexity_target,
                project_root=resolved_project_root,
            )
        )

        git_data, complexity_data = await asyncio.gather(git_task, complexity_task)

        target_key = None
        if file_path:
            target_key = self._derive_relative_key(git_target, file_path)
            git_data = self._filter_metrics(git_data, target_key, file_path)
            complexity_data = self._filter_metrics(complexity_data, target_key, file_path)

        debt_scores = self.debt_calculator.calculate_debt_score(git_data, complexity_data)

        if file_path:
            debt_scores = self._filter_metrics(debt_scores, target_key, file_path)

        return {
            'git_analysis': git_data,
            'complexity_analysis': complexity_data,
            'debt_scores': debt_scores,
            'timestamp': datetime.now().isoformat()
        }

    def _filter_metrics(self, metrics: Dict, target_key: Optional[str], file_path: str) -> Dict:
        if not metrics:
            return {}

        normalized_target = target_key or self._normalize_key(Path(file_path).name)
        filtered: Dict = {}

        for key, value in metrics.items():
            normalized_key = self._normalize_key(key)
            if normalized_key == normalized_target:
                filtered[key] = value
                continue

            if isinstance(value, dict):
                alt = value.get('relative_path') or value.get('absolute_path')
                if alt and self._normalize_key(alt) == normalized_target:
                    filtered[key] = value
                    continue

        return filtered

    def _derive_relative_key(self, project_path: str, file_path: str) -> Optional[str]:
        try:
            file_resolved = Path(file_path).resolve()
        except Exception:
            return None

        if project_path:
            root = Path(project_path).resolve()
            if root.is_file():
                root = root.parent
            try:
                relative = file_resolved.relative_to(root)
                return self._normalize_key(relative.as_posix())
            except ValueError:
                pass

        return self._normalize_key(file_resolved.as_posix())

    def _normalize_key(self, value: str) -> str:
        if not value:
            return ''
        normalized = str(value).replace('\\', '/').rstrip('/')
        if os.name == 'nt':
            normalized = normalized.lower()
        return normalized