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


def _is_postgres_url(url: str) -> bool:
    if not url:
        return False
    sl = url.strip().lower()
    return sl.startswith("postgresql://") or sl.startswith("postgres://") or sl.startswith("postgresql+")


def get_sqlalchemy_url(*, default: str = "") -> str:
    """
    Prefer DATABASE_URL; if only DATABASE_DSN_ASYNC exists, derive a SQLAlchemy URL.
    """
    url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN") or ""
    if url:
        out = normalize_sqlalchemy_url(url)
        if not _is_postgres_url(out):
            raise RuntimeError(f"DATABASE_URL must be PostgreSQL. Got: {out.split('://', 1)[0] if '://' in out else out}")
        return out

    dsn_async = os.getenv("DATABASE_DSN_ASYNC") or ""
    if dsn_async:
        out = normalize_sqlalchemy_url(dsn_async)
        if not _is_postgres_url(out):
            raise RuntimeError("DATABASE_DSN_ASYNC must be PostgreSQL for Route A.")
        return out

    out = normalize_sqlalchemy_url(default)
    if not _is_postgres_url(out):
        raise RuntimeError("DATABASE_URL is required and must be PostgreSQL for Route A.")
    return out


def get_asyncpg_dsn(*, default: str = "") -> str:
    """
    Prefer DATABASE_DSN_ASYNC; else derive from DATABASE_URL by stripping driver suffix.
    """
    dsn_async = os.getenv("DATABASE_DSN_ASYNC") or ""
    if dsn_async:
        out = normalize_asyncpg_dsn(dsn_async)
        if not _is_postgres_url(out):
            raise RuntimeError("DATABASE_DSN_ASYNC must be PostgreSQL for Route A.")
        return out

    url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN") or ""
    if url:
        out = normalize_asyncpg_dsn(url)
        if not _is_postgres_url(out):
            raise RuntimeError("DATABASE_URL must be PostgreSQL for Route A.")
        return out

    out = normalize_asyncpg_dsn(default)
    if not _is_postgres_url(out):
        raise RuntimeError("DATABASE_DSN_ASYNC is required and must be PostgreSQL for Route A.")
    return out

