# app/analysis/git_analyzer.py
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Dict, Optional

from git import GitCommandError, InvalidGitRepositoryError, NoSuchPathError
from pydriller import Repository

from app.analysis.base import BaseAnalyzer


logger = logging.getLogger(__name__)


class GitHistoryAnalyzer(BaseAnalyzer):
    """Git历史分析器"""

    async def analyze(self, project_path: str) -> Dict:
        repo_root = self._resolve_repo_root(project_path)
        heat_data: Dict[str, Dict] = {}
        tracked_exts = {'.py', '.js', '.ts', '.java', '.go', '.cpp', '.c', '.jsx', '.tsx'}

        try:
            repository = Repository(str(repo_root))
        except (InvalidGitRepositoryError, NoSuchPathError, GitCommandError) as exc:
            logger.warning("Git history unavailable at %s: %s", repo_root, exc)
            return {}
        except Exception as exc:  # defensive catch-all
            logger.exception("Unexpected git analysis failure for %s", repo_root)
            return {}

        try:
            for commit in repository.traverse_commits():
                commit_time = self._ensure_timezone(commit.committer_date)
                author_name = commit.author.name or "unknown"

                for file in commit.modified_files:
                    rel_path = self._resolve_file_path(file)
                    if not rel_path:
                        continue

                    if Path(rel_path).suffix.lower() not in tracked_exts:
                        continue

                    entry = heat_data.setdefault(rel_path, {
                        'change_count': 0,
                        'authors': set(),
                        'last_modified': None,
                        'added_lines': 0,
                        'deleted_lines': 0,
                    })

                    entry['change_count'] += 1
                    entry['authors'].add(author_name)
                    entry['added_lines'] += abs(file.added_lines or 0)
                    entry['deleted_lines'] += abs(file.deleted_lines or 0)
                    entry['last_modified'] = commit_time if not entry['last_modified'] or commit_time > entry['last_modified'] else entry['last_modified']
        except (InvalidGitRepositoryError, NoSuchPathError, GitCommandError) as exc:
            logger.warning("Git history traversal failed at %s: %s", repo_root, exc)
            return {}
        except Exception as exc:
            logger.exception("Unexpected git history traversal failure at %s", repo_root)
            return {}

        return self._calculate_heat_scores(heat_data)

    def _calculate_heat_scores(self, heat_data: Dict) -> Dict:
        """计算热点分数"""
        scores = {}
        now = datetime.now(timezone.utc)

        for file_path, data in heat_data.items():
            change_score = min(data['change_count'] / 5, 1.0)
            churn = data['added_lines'] + data['deleted_lines']
            churn_score = min(churn / 400, 1.0)
            author_diversity = min(len(data['authors']) / 4, 1.0)

            recency_score = 0.0
            if data['last_modified']:
                age_days = max(0, (now - data['last_modified']).days)
                if age_days <= 7:
                    recency_score = 1.0
                else:
                    recency_score = max(0.0, 1 - age_days / 180)
            heat_score = min(1.0, 0.35 * change_score + 0.3 * churn_score + 0.2 * author_diversity + 0.15 * recency_score)

            scores[file_path] = {
                'heat_score': heat_score,
                'change_count': data['change_count'],
                'author_count': len(data['authors']),
                'churn': churn,
                'last_modified': data['last_modified'].isoformat() if data['last_modified'] else None,
                'score_breakdown': {
                    'change_score': change_score,
                    'churn_score': churn_score,
                    'author_diversity': author_diversity,
                    'recency_score': recency_score,
                }
            }

        return scores

    def _resolve_repo_root(self, project_path: str) -> Path:
        candidate = Path(project_path).resolve()
        return candidate if candidate.is_dir() else candidate.parent

    def _resolve_file_path(self, file) -> Optional[str]:
        rel_path = file.new_path or file.old_path or file.filename
        if not rel_path:
            return None
        return str(Path(rel_path).as_posix())

    def _ensure_timezone(self, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)