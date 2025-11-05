# app/analysis/git_analyzer.py
from typing import Dict

from pydriller import Repository

from app.analysis.base import BaseAnalyzer


class GitHistoryAnalyzer(BaseAnalyzer):
    """Git历史分析器"""

    async def analyze(self, project_path: str) -> Dict:
        heat_data = {}

        for commit in Repository(project_path).traverse_commits():
            for file in commit.modified_files:
                if file.filename not in heat_data:
                    heat_data[file.filename] = {
                        'change_count': 0,
                        'authors': set(),
                        'last_modified': commit.committer_date,
                        'complexity_changes': []
                    }

                heat_data[file.filename]['change_count'] += 1
                heat_data[file.filename]['authors'].add(commit.author.name)
                heat_data[file.filename]['last_modified'] = commit.committer_date

        return self._calculate_heat_scores(heat_data)

    def _calculate_heat_scores(self, heat_data: Dict) -> Dict:
        """计算热点分数"""
        scores = {}
        for file_path, data in heat_data.items():
            # 基于修改频率和作者数量计算热度
            change_score = min(data['change_count'] / 10, 1.0)  # 归一化
            author_diversity = min(len(data['authors']) / 5, 1.0)

            heat_score = (change_score * 0.7 + author_diversity * 0.3)
            scores[file_path] = {
                'heat_score': heat_score,
                'change_count': data['change_count'],
                'author_count': len(data['authors']),
                'last_modified': data['last_modified'].isoformat()
            }

        return scores