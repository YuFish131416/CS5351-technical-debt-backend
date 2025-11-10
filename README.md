## Technical Debt Manager — 启动说明

本仓库是一个基于 FastAPI 的后端服务（入口文件为 `main.py`）。下面给出在 Windows（PowerShell）下的本地启动步骤、常用脚本和注意事项。

## 系统要求
- Python 3.10+（建议使用 3.11）
- Git（可选）
- Redis（如果要运行 Celery worker 作为任务队列）

项目依赖已列在 `requirements.txt` 中（包含 FastAPI、Uvicorn、SQLAlchemy、Celery、PyDriller、radon 等）。

## 环境变量
项目通过 `pydantic` 的 `BaseSettings` 从 `.env` 中读取配置。至少需要设置以下变量：
## Technical Debt Manager — 启动与运行说明（已更新）

此仓库是一个基于 FastAPI 的后端服务，ASGI app 在 `main.py` 中以 `app` 暴露（即 `main:app`）。本文档包含 Windows（PowerShell）上的本地开发启动、依赖、常用脚本、以及迁移/归档脚本的说明。

重要变更摘要（2025）：
- 项目响应已对外暴露 camelCase 别名（例如 `localPath`, `currentAnalysisId`），以兼容前端期望。
- 已实现对 Windows 本地路径的归一化（查询时对 `local_path`/`file_path` 做 normpath、反斜杠->斜杠、去尾斜杠并在 Windows 上小写），以避免路径格式导致的匹配失败。
- 一次性迁移脚本与临时诊断脚本已被归档到 `scripts/archive/migrations/`，避免仓库根目录混乱。请在必要时在归档目录中找到历史脚本并在受控环境下运行。

## 系统要求
- Python 3.10+（建议 3.11）
- Git（可选）
- Redis（如果要运行 Celery worker 作为任务队列）

依赖已列在 `requirements.txt`（FastAPI、Uvicorn、SQLAlchemy、Celery、PyDriller、radon 等）。另外，配置模块使用 `pydantic-settings`，若运行时报错请安装它：

```powershell
pip install pydantic-settings
```

## 环境变量
通过 pydantic 从 `.env` 读取配置。至少需要：
- `DATABASE_URL`（必需）
- `REDIS_URL`（用于 Celery broker/result，开发环境可指向本地 Redis）
- `SECRET_KEY`

示例（SQLite + 本地 Redis）：

```env
DATABASE_URL=sqlite:///./dev.db
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-secret-key
```

若使用 Postgres，格式示例：
`postgresql+psycopg2://user:password@host:5432/dbname`

## 本地开发（PowerShell）

1. 在项目根打开 PowerShell。
2. 创建并激活虚拟环境：

```powershell
python -m venv .venv
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process -Force
. .\\.venv\\Scripts\\Activate.ps1
```

3. 安装依赖：

```powershell
pip install -r requirements.txt
pip install pydantic-settings
```

4. 创建 `.env` 并填入必需变量。

5. 启动开发服务器（推荐绑定到本地回环地址）：

```powershell
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

访问： http://127.0.0.1:8000 ，自动文档位于 `/docs`。

## 启动脚本
- `start.ps1`：PowerShell 脚本（会帮助创建 venv/安装依赖并启动服务）。
- `start.cmd`：Windows 批处理脚本。

示例：

```powershell
# 在项目根运行
.\\start.ps1
```

## Celery（后台任务）

1. 确保 `REDIS_URL` 已配置且 Redis 服务已启动。
2. 在激活虚拟环境后启动 worker（在新终端中）：

```powershell
celery -A app.tasks.celery_app.celery worker --loglevel=info
```

注意：若 `celery` 命令不可用，请确认虚拟环境已激活并且 celery 已安装。

## 数据库与一次性迁移脚本（注意）

此仓库使用 SQLAlchemy。`main.py` 在 dev 启动时会调用 `Base.metadata.create_all(bind=engine)` 来创建表结构（适合开发）。生产环境请使用迁移工具（强烈建议 Alembic）。

我们保留了少量“一次性迁移脚本”（用于修补旧表结构），但这些脚本已移到：

```
scripts/archive/migrations/
```

如果需要运行某个归档脚本（仅供紧急或手工修复），请在项目根以 `PYTHONPATH` 可见项目包的方式运行。例如（PowerShell）：

```powershell
#$env:PYTHONPATH = (Get-Location).Path  # 如果你需要临时使 app 包可导入
#$env:PYTHONPATH = (Get-Location).Path; python .\\scripts\\archive\\migrations\\db_migrate_add_debt_fields.py

# 推荐的安全运行方式（不会自动修改生产数据库，先打印目标 DB）
$env:PYTHONPATH = (Get-Location).Path; python .\\scripts\\archive\\migrations\\db_migrate_add_debt_fields.py
```

请务必在运行前：
- 确认 `DATABASE_URL` 指向正确的数据库实例；
- 在生产执行前做备份；
- 优先考虑把这些改动迁入 Alembic migration，而非长期依赖手工脚本。

## 重要端点变更（供前端参考）
- POST /api/v1/projects/ 现在对 `localPath` 做去重（返回 camelCase 字段），若重复返回 200 与已有项目；创建返回 201。 
- POST /api/v1/projects/{id}/analysis 返回立即的 `analysis_id`（Celery task_id），并返回 202/503/409 等语义化状态。
- GET /api/v1/projects/by-path?localPath=... 支持 Windows 路径归一化。
- GET /api/v1/debts/project/{project_id}?file_path=... 同样支持路径归一化以匹配存储路径。

## 运行测试

```powershell
pip install pytest
pytest -q
```

## 常见故障排查
- ModuleNotFoundError：确认虚拟环境激活并已安装 `requirements.txt` 与 `pydantic-settings`。
- 数据库列缺失（如 `line` 或 `project_metadata`）：仓库包含归档迁移脚本可手动运行（见上文）。
- Celery 无法连接 broker：检查 `REDIS_URL` 并确认 Redis 在运行。

---

如果你希望，我可以：
- 把这些一次性迁移脚本转换为 Alembic revisions（推荐，需添加 alembic 依赖并初始化迁移目录）；
- 生成 `docker-compose.yml`（含 Postgres + Redis + 后端）并写入运行/开发示例。

如需其他更新（英文版 README、CI 示例或更严格的迁移流程），告诉我你要优先的项，我会继续实现。

祝开发顺利！
