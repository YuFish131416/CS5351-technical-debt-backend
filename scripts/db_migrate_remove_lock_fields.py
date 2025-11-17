"""
One-off migration: remove manual lock columns from projects table (Postgres).

Usage:
    python scripts/db_migrate_remove_lock_fields.py

This script is safe to run multiple times; it uses IF EXISTS checks.
Run it after taking a backup of your DB.
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
                "ALTER TABLE projects DROP COLUMN IF EXISTS locked_by;",
                "ALTER TABLE projects DROP COLUMN IF EXISTS lock_expires_at;",
            ]
            for s in stmts:
                print('Executing:', s)
                conn.execute(text(s))
        else:
            print('This migration script currently supports Postgres only. Dialect:', dialect)

    print('Migration completed')


if __name__ == '__main__':
    main()
