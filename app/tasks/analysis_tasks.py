import asyncio
import json
from datetime import datetime
from pathlib import Path

from celery.utils.log import get_task_logger

from app.models.debt import TechnicalDebt
from app.models.project import Project
from app.tasks.celery_app import celery_app
from app.core.database import SessionLocal
from app.services.analysis_orchestrator import AnalysisOrchestrator
from app.repositories.project_repository import ProjectRepository
from app.repositories.debt_repository import DebtRepository


logger = get_task_logger(__name__)
LOG_FILE_PATH = Path(__file__).resolve().parents[2] / 'logs' / 'analysis_scan.log'


def _ensure_log_file():
    try:
        LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not LOG_FILE_PATH.exists():
            LOG_FILE_PATH.touch(exist_ok=True)
    except Exception:
        logger.exception("Failed to prepare analysis log file")


_ensure_log_file()


@celery_app.task(bind=True)
def analyze_project_task(self, project_id: int, file_path: str = None):
    """异步分析项目任务"""
    db = SessionLocal()
    try:
        project_repo = ProjectRepository(Project, db)
        debt_repo = DebtRepository(TechnicalDebt, db)

        project = project_repo.get(project_id)
        if not project:
            return {"status": "error", "message": "Project not found"}

        # 执行分析
        orchestrator = AnalysisOrchestrator()
        # 如果提供 file_path，则将其作为分析目标（orchestrator 可选择支持）
        target = project.local_path
        if file_path:
            target = file_path

        # 在 DB 中标记 task 正在运行（current_analysis_id/status）
        try:
            task_id = getattr(self.request, 'id', None) or getattr(self, 'id', None)
            if task_id:
                project.current_analysis_id = task_id
                project.status = 'analyzing'
                db.add(project)
                db.commit()
        except Exception:
            db.rollback()

        # 更新任务状态到 Celery meta
        try:
            self.update_state(state='STARTED', meta={'message': 'analysis started', 'started_at': None, 'progress': 0})
        except Exception:
            pass

        analysis_result = asyncio.run(orchestrator.analyze_project(target))

        # 保存债务项目并在每个文件后更新任务进度
        debt_scores = analysis_result.get('debt_scores', {})
        total = max(1, len(debt_scores))
        processed = 0
        collected_scores = []
        for fpath, debt_data in debt_scores.items():
            severity = debt_data.get('severity', '') if isinstance(debt_data, dict) else ''
            debt_score = debt_data.get('debt_score', 0.0) if isinstance(debt_data, dict) else 0.0
            debt_item = {
                'project_id': project_id,
                'file_path': fpath,
                'line': debt_data.get('line') if isinstance(debt_data, dict) else None,
                'debt_type': 'hotspot',
                'severity': severity,
                'description': f"Technical debt hotspot: {debt_score:.2f} score",
                'estimated_effort': debt_data.get('estimated_effort'),
                'project_metadata': _serialize_metadata(debt_data)
            }
            try:
                debt_repo.create(debt_item)
            except Exception:
                # don't fail whole task on single debt save error
                pass

            collected_scores.append({
                'file_path': fpath,
                'debt_score': debt_score,
                'severity': severity,
                'metadata': debt_data,
            })
            logger.info("Debt score | project=%s | file=%s | score=%.4f | severity=%s", project_id, fpath, debt_score, severity)

            processed += 1
            # 更新 Celery 任务状态进度
            try:
                progress = int(processed / total * 100)
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'message': 'processing',
                        'progress': progress,
                        'processed': processed,
                        'total': total,
                        'last_file': fpath,
                        'last_score': debt_score,
                        'last_severity': severity,
                    }
                )
            except Exception:
                pass

        # 标记为完成并返回信息；更新项目表
        try:
            task_id = getattr(self.request, 'id', None) or getattr(self, 'id', None)
            project.current_analysis_id = None
            project.last_analysis_id = task_id
            project.last_analysis_at = datetime.now()
            project.status = 'idle'
            db.add(project)
            db.commit()
        except Exception:
            db.rollback()

        _write_scan_log(project_id, collected_scores)

        return {
            "status": "completed",
            "project_id": project_id,
            "finished_at": datetime.now().isoformat(),
            "debt_scores": collected_scores,
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


def _serialize_metadata(payload):
    if payload is None:
        return None
    try:
        return json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps(str(payload), ensure_ascii=False)


def _write_scan_log(project_id: int, entries):
    if not entries:
        record = {
            'timestamp': datetime.now().isoformat(),
            'project_id': project_id,
            'file_path': None,
            'debt_score': 0.0,
            'severity': 'none',
            'details': 'No files analyzed or results empty',
        }
        try:
            with LOG_FILE_PATH.open('a', encoding='utf-8') as log_file:
                log_file.write(json.dumps(record, ensure_ascii=False) + '\n')
        except Exception:
            logger.exception("Failed to write empty analysis record")
        return

    try:
        with LOG_FILE_PATH.open('a', encoding='utf-8') as log_file:
            for entry in entries:
                details_raw = entry.get('metadata')
                if details_raw is None:
                    details = None
                else:
                    try:
                        json.dumps(details_raw, ensure_ascii=False)
                        details = details_raw
                    except (TypeError, ValueError):
                        details = str(details_raw)

                record = {
                    'timestamp': datetime.now().isoformat(),
                    'project_id': project_id,
                    'file_path': entry.get('file_path'),
                    'debt_score': entry.get('debt_score', 0.0),
                    'severity': entry.get('severity') or 'low',
                    'details': details,
                }
                log_file.write(json.dumps(record, ensure_ascii=False) + '\n')
    except Exception:
        logger.exception("Failed to write analysis scan log")
