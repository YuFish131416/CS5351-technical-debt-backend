# app/analysis/code_analyzer.py
from typing import Dict, List

import radon
from radon.complexity import cc_visit
from radon.metrics import mi_visit
from radon.raw import analyze

from app.analysis.base import BaseAnalyzer


class CodeComplexityAnalyzer(BaseAnalyzer):
    """代码复杂度分析器"""

    async def analyze(self, project_path: str) -> Dict:
        complexity_data = {}

        for file_path in self._find_source_files(project_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    source_code = f.read()

                # 圈复杂度分析
                complexity_results = cc_visit(source_code)
                avg_complexity = self._calculate_avg_complexity(complexity_results)

                # 维护性指数
                maintainability_index = mi_visit(source_code, multi=True)

                # 原始指标（行数等）
                raw_metrics = analyze(source_code)

                complexity_data[file_path] = {
                    'avg_complexity': avg_complexity,
                    'maintainability_index': maintainability_index,
                    'lines_of_code': raw_metrics.loc,
                    'comment_density': raw_metrics.comments / raw_metrics.loc if raw_metrics.loc > 0 else 0,
                    'function_count': len(complexity_results)
                }

            except Exception as e:
                print(f"Error analyzing {file_path}: {e}")
                continue

        return complexity_data

    def _find_source_files(self, project_path: str) -> List[str]:
        """查找源代码文件"""
        # 实现文件查找逻辑
        pass

    def _calculate_avg_complexity(self, complexity_results: List) -> float:
        if not complexity_results:
            return 0.0
        return sum([result.complexity for result in complexity_results]) / len(complexity_results)