"""运行一次性迁移：为 projects 表添加锁/状态/analysis 字段，并添加 local_path 唯一约束（Postgres）。

用法：在项目根激活虚拟环境后运行：
    python scripts/archive/migrations/db_migrate_add_project_fields.py

注意：脚本仅对 Postgres 做了安全检查并使用 IF NOT EXISTS 语句；请在生产前备份数据库。
"""
from sqlalchemy import create_engine, text
from app.core.config import settings


def main():
    url = settings.DATABASE_URL
    engine = create_engine(url)

    with engine.connect() as conn:
        dialect = conn.dialect.name
        print('DB dialect:', dialect)
        if dialect.startswith('postgres'):
            stmts = [
                "ALTER TABLE projects ADD COLUMN IF NOT EXISTS locked_by varchar(100);",
                "ALTER TABLE projects ADD COLUMN IF NOT EXISTS lock_expires_at timestamptz;",
                "ALTER TABLE projects ADD COLUMN IF NOT EXISTS status varchar(50) DEFAULT 'idle';",
                "ALTER TABLE projects ADD COLUMN IF NOT EXISTS current_analysis_id varchar(100);",
                "ALTER TABLE projects ADD COLUMN IF NOT EXISTS last_analysis_id varchar(100);",
                "ALTER TABLE projects ADD COLUMN IF NOT EXISTS last_analysis_at timestamptz;",
            ]
            for s in stmts:
                print('Executing:', s)
                conn.execute(text(s))

            # add unique constraint if not exists
            uq_check = text("SELECT 1 FROM pg_constraint WHERE conname = 'uq_projects_local_path';")
            res = conn.execute(uq_check).fetchone()
            if not res:
                print('Adding unique constraint on local_path')
                conn.execute(text("ALTER TABLE projects ADD CONSTRAINT uq_projects_local_path UNIQUE (local_path);"))
            else:
                print('Unique constraint already exists')
        else:
            print('This migration script currently supports Postgres only. Dialect:', dialect)

    print('Migration completed')


if __name__ == '__main__':
    main()
