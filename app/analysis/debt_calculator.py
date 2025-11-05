# app/analysis/debt_calculator.py
from typing import Dict


class TechnicalDebtCalculator:
    """技术债务计算器"""

    def calculate_debt_score(self, heat_data: Dict, complexity_data: Dict) -> Dict:
        """计算技术债务分数"""
        debt_scores = {}

        for file_path in set(heat_data.keys()) | set(complexity_data.keys()):
            heat_score = heat_data.get(file_path, {}).get('heat_score', 0)
            complexity_score = self._normalize_complexity(
                complexity_data.get(file_path, {}).get('avg_complexity', 0)
            )

            # 综合债务分数
            debt_score = (heat_score * 0.6 + complexity_score * 0.4)

            debt_scores[file_path] = {
                'debt_score': debt_score,
                'severity': self._classify_severity(debt_score),
                'estimated_effort': self._estimate_effort(debt_score, complexity_data.get(file_path, {})),
                'heat_metrics': heat_data.get(file_path),
                'complexity_metrics': complexity_data.get(file_path)
            }

        return debt_scores

    def _normalize_complexity(self, complexity: float) -> float:
        """归一化复杂度分数"""
        return min(complexity / 20, 1.0)  # 假设20为高复杂度阈值

    def _classify_severity(self, score: float) -> str:
        """分类严重程度"""
        if score >= 0.8:
            return 'critical'
        elif score >= 0.6:
            return 'high'
        elif score >= 0.4:
            return 'medium'
        else:
            return 'low'

    def _estimate_effort(self, score: float, metrics: Dict) -> int:
        """估算修复工作量（小时）"""
        base_effort = score * 16  # 最大16小时
        size_factor = metrics.get('lines_of_code', 0) / 500  # 每500行调整
        return max(1, int(base_effort * size_factor))