# app/analysis/debt_calculator.py
from math import ceil
from typing import Dict, List


class TechnicalDebtCalculator:
    """技术债务计算器"""

    def calculate_debt_score(self, heat_data: Dict, complexity_data: Dict) -> Dict:
        """计算技术债务分数，并提供更精细的风险拆解"""
        debt_scores: Dict[str, Dict] = {}
        all_files = set(heat_data.keys()) | set(complexity_data.keys())

        for file_path in all_files:
            heat_metrics = heat_data.get(file_path, {}) or {}
            complexity_metrics = complexity_data.get(file_path, {}) or {}

            heat_component = self._heat_component(heat_metrics)
            complexity_component = self._complexity_component(complexity_metrics)
            maintainability_component = self._maintainability_component(complexity_metrics)
            size_component = self._size_component(complexity_metrics)
            comment_component = self._comment_component(complexity_metrics)
            smell_component = self._smell_component(complexity_metrics)

            debt_score = min(1.0, (
                heat_component * 0.3
                + complexity_component * 0.2
                + maintainability_component * 0.15
                + size_component * 0.1
                + comment_component * 0.05
                + smell_component * 0.2
            ))

            breakdown = {
                'heat_component': heat_component,
                'complexity_component': complexity_component,
                'maintainability_component': maintainability_component,
                'size_component': size_component,
                'comment_component': comment_component,
                'smell_component': smell_component,
            }

            severity = self._classify_severity(debt_score)
            debt_scores[file_path] = {
                'debt_score': debt_score,
                'severity': severity,
                'estimated_effort': self._estimate_effort(debt_score, complexity_metrics),
                'risk_flags': self._generate_flags(heat_metrics, complexity_metrics, breakdown),
                'heat_metrics': heat_metrics,
                'complexity_metrics': complexity_metrics,
                'score_breakdown': breakdown,
                'smell_flags': complexity_metrics.get('smell_flags', []),
                'smell_samples': complexity_metrics.get('smell_samples', {}),
                'line': self._derive_focus_line(complexity_metrics),
            }

        return debt_scores

    def _heat_component(self, metrics: Dict) -> float:
        base_score = metrics.get('heat_score', 0.0) or 0.0
        change_boost = min((metrics.get('change_count', 0) or 0) / 6, 1.0)
        churn = metrics.get('churn', 0) or 0
        churn_boost = min(churn / 500, 1.0)
        return max(base_score, 0.25 * change_boost + 0.75 * base_score + 0.15 * churn_boost)

    def _complexity_component(self, metrics: Dict) -> float:
        complexity = metrics.get('avg_complexity', 0.0) or 0.0
        max_complexity = metrics.get('max_complexity', complexity) or complexity
        # 更关注最高圈复杂度，提升敏感度
        return min(max_complexity / 8, 1.0)

    def _maintainability_component(self, metrics: Dict) -> float:
        mi = metrics.get('maintainability_index', 100.0) or 100.0
        return min(max((100 - mi) / 60, 0.0), 1.0)

    def _size_component(self, metrics: Dict) -> float:
        loc = metrics.get('lines_of_code', 0) or 0
        functions = metrics.get('function_count', 0) or 0
        loc_component = min(loc / 600, 1.0)
        function_component = min(functions / 30, 1.0)
        return max(loc_component, function_component)

    def _comment_component(self, metrics: Dict) -> float:
        density = metrics.get('comment_density', 0.0) or 0.0
        # 注释稀缺时增加债务分数
        if density >= 0.35:
            return 0.0
        return min((0.35 - density) / 0.35, 1.0)

    def _smell_component(self, metrics: Dict) -> float:
        score = metrics.get('smell_score', 0.0) or 0.0
        penalty = min(len(metrics.get('smell_flags', []) or []) / 4, 1.0)
        combined = max(score, penalty)
        longest_line = metrics.get('longest_line', 0) or 0
        if longest_line >= 220:
            combined = min(1.0, combined + 0.2)
        return min(1.0, combined)

    def _classify_severity(self, score: float) -> str:
        """分类严重程度"""
        if score >= 0.25:
            return 'critical'
        elif score >= 0.15:
            return 'high'
        elif score >= 0.05:
            return 'medium'
        return 'low'

    def _estimate_effort(self, score: float, metrics: Dict) -> int:
        """估算修复工作量（小时）"""
        loc = metrics.get('lines_of_code', 0) or 0
        complexity = metrics.get('avg_complexity', 0.0) or 0.0
        base = 2 + score * 10
        loc_bonus = loc / 250
        complexity_bonus = complexity / 2
        return max(1, ceil(base + loc_bonus + complexity_bonus))

    def _generate_flags(self, heat: Dict, complexity: Dict, breakdown: Dict) -> List[str]:
        flags: List[str] = []

        if breakdown['heat_component'] > 0.6:
            flags.append('Frequent changes / high churn')
        if breakdown['complexity_component'] > 0.6:
            flags.append('High cyclomatic complexity')
        if complexity.get('maintainability_index', 100) < 65:
            flags.append('Low maintainability index')
        if complexity.get('lines_of_code', 0) > 800:
            flags.append('Large file size')
        if breakdown['comment_component'] > 0.5:
            flags.append('Low comment coverage')
        if breakdown['smell_component'] > 0.5:
            flags.append('Code smell indicators present')

        for flag in complexity.get('smell_flags', []) or []:
            if flag not in flags:
                flags.append(flag)

        recent_score = (heat.get('score_breakdown', {}) or {}).get('recency_score', 0.0)
        if recent_score >= 0.8:
            flags.append('Recently modified hotspot')

        return flags

    def _derive_focus_line(self, metrics: Dict) -> int | None:
        if not metrics:
            return None

        def pick_first_line(entries: List[Dict] | None, primary: str = 'line', fallback: str = 'start_line') -> int | None:
            for entry in entries or []:
                for key in (primary, fallback):
                    value = entry.get(key)
                    if isinstance(value, (int, float)) and value > 0:
                        return int(value)
            return None

        line = pick_first_line(metrics.get('high_complexity_blocks') or [], 'start_line', 'line')
        if line:
            return line

        line = pick_first_line(metrics.get('deeply_nested_functions') or [])
        if line:
            return line

        line = pick_first_line(metrics.get('long_parameter_functions') or [], 'line', 'start_line')
        if line:
            return line

        line = pick_first_line(metrics.get('complex_conditionals') or [])
        if line:
            return line

        line = pick_first_line(metrics.get('uninformative_identifiers') or [])
        if line:
            return line

        samples = metrics.get('smell_samples') or {}
        long_functions = samples.get('long_functions') or []
        line = pick_first_line(long_functions, 'start_line', 'line')
        if line:
            return line

        for item in samples.get('long_lines') or []:
            if isinstance(item, (list, tuple)) and item:
                candidate = item[0]
                if isinstance(candidate, (int, float)) and candidate > 0:
                    return int(candidate)

        line = pick_first_line(samples.get('complex_conditionals') or [])
        if line:
            return line

        if (metrics.get('lines_of_code') or 0) > 0:
            return 1

        return None