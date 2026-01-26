from __future__ import annotations

import os


def normalize_sqlalchemy_url(url: str) -> str:
    """
    Normalize a Postgres URL for SQLAlchemy (sync).
    - postgresql:// or postgres://  -> postgresql+psycopg2://
    - postgresql+psycopg2:// stays
    - sqlite:// stays
    """
    if not url:
        return url
    s = url.strip().strip('"').strip("'")
    sl = s.lower()
    if sl.startswith("sqlite"):
        return s
    if sl.startswith("postgresql+psycopg2://"):
        return s
    if sl.startswith("postgresql+psycopg://"):
        # keep psycopg (v3) if user wants it
        return s
    if sl.startswith("postgresql://"):
        return "postgresql+psycopg2://" + s[len("postgresql://") :]
    if sl.startswith("postgres://"):
        return "postgresql+psycopg2://" + s[len("postgres://") :]
    return s


def normalize_asyncpg_dsn(dsn: str) -> str:
    """
    Normalize a DSN for asyncpg.
    - postgresql+psycopg2:// -> postgresql://
    - postgresql+psycopg://  -> postgresql://
    """
    if not dsn:
        return dsn
    s = dsn.strip().strip('"').strip("'")
    s = s.replace("postgresql+psycopg2://", "postgresql://", 1)
    s = s.replace("postgresql+psycopg://", "postgresql://", 1)
    s = s.replace("postgres+psycopg://", "postgresql://", 1)
    return s


def get_sqlalchemy_url(*, default: str = "") -> str:
    """
    Prefer DATABASE_URL; if only DATABASE_DSN_ASYNC exists, derive a SQLAlchemy URL.
    """
    url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN") or ""
    if url:
        return normalize_sqlalchemy_url(url)

    dsn_async = os.getenv("DATABASE_DSN_ASYNC") or ""
    if dsn_async:
        return normalize_sqlalchemy_url(dsn_async)

    return normalize_sqlalchemy_url(default)


def get_asyncpg_dsn(*, default: str = "") -> str:
    """
    Prefer DATABASE_DSN_ASYNC; else derive from DATABASE_URL by stripping driver suffix.
    """
    dsn_async = os.getenv("DATABASE_DSN_ASYNC") or ""
    if dsn_async:
        return normalize_asyncpg_dsn(dsn_async)

    url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN") or ""
    if url:
        return normalize_asyncpg_dsn(url)

    return normalize_asyncpg_dsn(default)

