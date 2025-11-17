# Technical Debt Backend

Technical Debt Backend 为 VS Code 扩展提供技术债务分析服务，负责接收项目或文件分析请求、运行热点与复杂度评估，并将结果以结构化数据持久化。本文档描述后端的架构、算法、接口、运行方式及扩展方案。

---

## 1. 架构概览

```
VS Code Extension ──HTTP──> FastAPI (app/api/*)
                               │
                               ├── AnalysisOrchestrator (app/services/analysis_orchestrator.py)
                               │       ├── GitHistoryAnalyzer  (app/analysis/git_analyzer.py)
                               │       ├── CodeComplexityAnalyzer (app/analysis/code_analyzer.py)
                               │       └── TechnicalDebtCalculator (app/analysis/debt_calculator.py)
                               │
                               └── Celery Worker (app/tasks/analysis_tasks.py)
                                       └── PostgreSQL (projects, technical_debts)
```

- **FastAPI**：提供 REST 接口，协调数据库访问与分析流程。
- **AnalysisOrchestrator**：并发调用 Git 与代码分析器，统一输出数据模型。
- **Celery**：执行长耗时或批量分析任务，复用与 API 相同的分析逻辑。
- **PostgreSQL**：存储项目、债务记录及完整分析元数据。
- **日志系统**：所有分析结果与异常写入 `logs/analysis_scan.log`。

---

## 2. 目录结构

| 路径 | 说明 |
| --- | --- |
| `app/api` | FastAPI 路由层。`projects.py` 管理项目与全量分析；`debts.py` 处理债务查询、状态变更与内联分析。 |
| `app/analysis` | 核心算法模块：`git_analyzer.py`、`code_analyzer.py`、`debt_calculator.py`、`base.py`。 |
| `app/services` | 服务层。`analysis_orchestrator.py` 调度分析；`project_service.py` 封装项目业务流程。 |
| `app/repositories` | 数据访问层，封装 SQLAlchemy 查询与更新。 |
| `app/models` | ORM 定义，包括 `Project`, `TechnicalDebt`, `CodeAnalysis` 等。 |
| `app/tasks` | Celery worker 定义与分析任务实现。 |
| `logs/analysis_scan.log` | 分析日志文件。 |
| `scripts/` | 数据迁移与调试脚本。 |

---

## 3. 分析管线

### 3.1 AnalysisOrchestrator

`analyze_project(project_path, file_path=None)`：

1. 解析输入路径，生成统一键值用于匹配分析输出。
2. 并发执行 `GitHistoryAnalyzer.analyze` 与 `CodeComplexityAnalyzer.analyze`。
3. 将结果传入 `TechnicalDebtCalculator.calculate_debt_score`，生成债务分数、风险标记及元数据。
4. 单文件模式下仅返回匹配文件；目录模式下返回全部分析结果。

### 3.2 GitHistoryAnalyzer

位置：`app/analysis/git_analyzer.py`

- 依赖 PyDriller 遍历 Git 提交。
- 原始指标：
  - `change_count`
  - `added_lines`、`deleted_lines`
  - `authors`（去重）
  - `last_modified`（UTC）
- 支持的扩展名：`.py`, `.js`, `.jsx`, `.ts`, `.tsx`, `.java`, `.go`, `.cpp`, `.c`
- 热点评分：`heat_score = min(1, 0.35*change + 0.3*churn + 0.2*author + 0.15*recency)`，其中 `recency_score` 按 7/180 天阈值衰减。
- 异常处理：对无法访问的仓库写 warning，并返回空 dict。

### 3.3 CodeComplexityAnalyzer

位置：`app/analysis/code_analyzer.py`

- 支持扩展名：`.py`, `.js`, `.jsx`, `.ts`, `.tsx`, `.java`, `.go`, `.cpp`, `.c`, `.map`, `.json`, `.css`, `.html`
- 排除目录：`.git`, `.hg`, `.svn`, `node_modules`, `.venv`, `venv`, `__pycache__`, `dist`, `build`

#### Python 文件

- Radon：`cc_visit`、`mi_visit`、`radon.raw.analyze`
- AST 分析：
  - 深度嵌套 (`max_nesting_depth` ≥ 4)
  - 参数数量 (`long_parameter_functions`)
  - 复杂布尔 (`complex_conditionals`)
  - 短命名 (`uninformative_identifiers`)
- 长行与长函数：阈值分别为 120/180 字符、80 行。

#### 非 Python 文件

- 启发式：行数、非空行、注释密度、最长行。
- 复用 `_detect_code_smells` 识别长行、长函数、深嵌套、复杂条件等。
- Minified 识别：根据最大行长、总行数判定是否压缩/混淆；`.map/.json` 自动标记。

#### 返回字段

- `language`
- `avg_complexity`, `max_complexity`
- `maintainability_index`
- `lines_of_code`, `logical_lines`, `comment_density`
- `smell_score`, `smell_flags`, `smell_samples`
- `longest_line`, `long_line_count`, `long_function_count`
- `high_complexity_blocks`, `deeply_nested_functions`, `long_parameter_functions`, `complex_conditionals`
- `is_minified_candidate`

### 3.4 TechnicalDebtCalculator

位置：`app/analysis/debt_calculator.py`

- 组件权重：
  - 热点 `0.30`
  - 复杂度 `0.20`
  - 维护性 `0.15`
  - 规模 `0.10`
  - 注释稀缺 `0.05`
  - 代码异味 `0.20`
- 输出：
  - `debt_score` (0~1)
  - `severity`：`low`, `medium`, `high`, `critical`
  - `estimated_effort`：`ceil(2 + score*10 + LOC/250 + avg_complexity/2)`
  - `risk_flags`：结合热点、复杂度、注释、smell 等指标
  - `score_breakdown`
  - `line`：`_derive_focus_line` 从复杂度块、深嵌套、长行、样本中推导代表性行号

### 3.5 支持的后缀

`SUPPORTED_SUFFIXES` 定义于 `app/api/projects.py`，与分析器保持同步，确保项目全量分析仅处理后端能够解析的文件类型。

---

## 4. REST API

### 4.1 Projects

| Method | Endpoint | 描述 |
| --- | --- | --- |
| `POST` | `/api/v1/projects/` | 创建项目，按 `local_path` 去重。 |
| `GET` | `/api/v1/projects/` | 返回项目列表，支持 `skip`、`limit`。 |
| `GET` | `/api/v1/projects/{id}` | 获取项目详情。 |
| `GET` | `/api/v1/projects/by-path` | 通过 `localPath` 查询项目。 |
| `GET` | `/api/v1/projects/{id}/current` | 遍历项目目录，对受支持文件运行分析并持久化结果。 |
| `POST` | `/api/v1/projects/{id}/analysis` | 触发 Celery 异步分析，可选 `file_path`。 |
| `GET` | `/api/v1/projects/{id}/analysis/{analysis_id}` | 查询异步任务状态。 |
| `GET` | `/api/v1/projects/{id}/debt-summary` | 聚合严重度与估算工时统计。 |

### 4.2 Debts

| Method | Endpoint | 描述 |
| --- | --- | --- |
| `GET` | `/api/v1/debts/project/{project_id}` | 获取项目债务。`file_path` 参数命中真实文件时触发内联分析。返回 `metadata`，即 `project_metadata` 的 JSON 反序列化。 |
| `PUT` | `/api/v1/debts/{debt_id}` | 更新债务状态，返回最新 `metadata`。 |

### 4.3 错误策略

- 所有错误均返回结构化 JSON，包含 `error`, `message`, `service`（若适用）。
- 常见状态码：
  - `400`：参数或业务校验失败。
  - `404`：项目或文件不存在。
  - `423`：项目正在分析。
  - `503`：依赖（Redis/数据库）不可用。
- 虚拟文档或缺失文件在日志中记录 `virtual_path_skipped`、`file_not_found` 等 detail。

---

## 5. 数据模型

### 5.1 projects 表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | INTEGER | 主键 |
| `name` | VARCHAR | 项目名称 |
| `local_path` | VARCHAR | 工作区根路径，唯一约束 `uq_projects_local_path` |
| `status` | VARCHAR | `idle`, `queued`, `analyzing` 等 |
| `current_analysis_id` | VARCHAR | 当前 Celery 任务 ID |
| `last_analysis_id` | VARCHAR | 最近完成任务 ID |
| `last_analysis_at` | TIMESTAMP | 最近分析完成时间 |

### 5.2 technical_debts 表

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | INTEGER | 主键 |
| `project_id` | INTEGER | 外键：projects.id |
| `file_path` | VARCHAR | 相对路径，小写、`/` 分隔 |
| `line` | INTEGER | 重点行号，可空 |
| `debt_type` | VARCHAR | `hotspot` |
| `severity` | VARCHAR | `low`, `medium`, `high`, `critical` |
| `description` | TEXT | 例如 `Technical debt hotspot: 0.32 score` |
| `estimated_effort` | INTEGER | 预计修复工时（小时） |
| `status` | VARCHAR | `open`, `in_progress`, `resolved`, `ignored` |
| `project_metadata` | JSON | 完整分析数据（热度、复杂度、异味、样本、风险标记等） |
| `created_at`, `updated_at` | TIMESTAMP | 审计字段 |

### 5.3 日志

- `logs/analysis_scan.log`：数组形式记录每次分析结果。字段示例：
  - `file_path`
  - `debt_score`
  - `severity`
  - `metadata.detail`（含错误描述或 info 提示）

---

## 6. 路径解析与过滤

- `_resolve_target_path`（`app/api/debts.py`）：
  - 处理绝对/相对路径组合，优先返回存在的真实路径。
  - 基于项目 `local_path` 进行大小写不敏感匹配，并容忍前导下划线差异。
  - 对虚拟文档（`extension-output-`, `untitled:`, `vscode-remote://` 等）直接返回 info 级结果而不抛错。
- `_normalize_storage_path`：统一存储路径格式（小写、`/` 分隔、无尾部 `/`）。
- `_choose_storage_path`：优先选用复杂度指标中的 `relative_path`，再退回原始键或绝对路径。
- `SUPPORTED_SUFFIXES`：`app/api/projects.py` 中定义，项目级分析仅处理这些后缀。

---

## 7. Celery 任务流程

- 入口：`app/tasks/analysis_tasks.py::analyze_project_task(project_id, file_path=None)`
- 步骤：
  1. 查询项目并解析 `local_path`。
  2. 调用 `AnalysisOrchestrator` 执行分析。
  3. `_persist_debt_scores` 写入 `technical_debts`，`_write_scan_log` 记录日志。
  4. 更新项目状态与任务 ID。
  5. 捕获异常时恢复项目状态并记录错误。

---

## 8. 部署与运行

### 8.1 本地开发

```powershell
cd backend/CS5351-technical-debt-backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
celery -A app.tasks.celery_app worker --loglevel=info
```

- 使用 `test_main.http` 或 REST Client 调试接口。
- 监控 `logs/analysis_scan.log` 及控制台日志了解分析过程。

### 8.2 环境变量

| 变量 | 示例 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg2://user:password@localhost:5432/technical_debt` | PostgreSQL 连接串 |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery Broker 与 Backend |
| `LOG_LEVEL` | `INFO` | FastAPI 日志等级 |

### 8.3 生产建议

- 使用 Supervisor、systemd 或容器编排托管 Uvicorn 与 Celery。
- 启用 HTTPS，配置健康检查与连接池。
- 监控 PostgreSQL、Redis 状态并启用备份策略。
- 集成日志收集系统聚合 `analysis_scan.log` 与服务日志。

---

## 9. 开发与扩展

- **新增语言**：在 `SUPPORTED_SUFFIXES`、`CodeComplexityAnalyzer._detect_language`、`_analyze_non_python` 中增加支持，并视需要调整 smell 识别逻辑。
- **调整权重**：修改 `TechnicalDebtCalculator` 中各组件函数，保持 `risk_flags` 与前端展示一致。
- **性能优化**：可引入结果缓存、拆分 Celery 任务或并行文件分析以缩短耗时。
- **故障排查**：
  - 查看 `analysis_scan.log` 获取分析明细。
  - 关注 FastAPI/Celery 日志判断依赖状态。
  - 使用 `scripts/inspect_project.py` 等脚本查询数据库。

---

## 10. 联系方式

- 技术支持：`YuFishYPH@gmail.com`
- 反馈渠道：GitHub Issues

---

Technical Debt Backend 为 VS Code 扩展提供稳定的技术债务检测与评估基础能力，可根据团队需求继续扩展语言支持、权重模型及集成方案。
