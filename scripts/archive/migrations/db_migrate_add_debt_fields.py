"""一次性迁移：为 technical_debts 表添加缺失的 line 列（Postgres）。

用法：在项目根激活虚拟环境后运行：
    python scripts/archive/migrations/db_migrate_add_debt_fields.py

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
                "ALTER TABLE technical_debts ADD COLUMN IF NOT EXISTS line integer;",
                "ALTER TABLE technical_debts ADD COLUMN IF NOT EXISTS project_metadata text;",
            ]
            for s in stmts:
                print('Executing:', s)
                conn.execute(text(s))
        else:
            print('This migration script currently supports Postgres only. Dialect:', dialect)

    print('Migration completed')


if __name__ == '__main__':
    main()
