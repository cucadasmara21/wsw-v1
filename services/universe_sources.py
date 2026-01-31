from __future__ import annotations

from typing import Literal

from config import settings


def legacy_assets_relation() -> str:
    """
    Legacy endpoints historically query FROM assets (unqualified).
    In Postgres mode, all legacy reads MUST go through public.universe_assets
    (canonical). Bootstrap may implement this as a TABLE or a VIEW over an
    existing legacy table.
    """
    return "assets" if settings.USE_SQLITE else "public.universe_assets"


def v8_universe_assets_relation() -> str:
    """
    Canonical V8 storage table.
    """
    return "universe_assets" if settings.USE_SQLITE else "public.universe_assets"


def v8_snapshot_relation(prefer_mv: bool = True) -> str:
    """
    Preferred snapshot source name (string only; existence is checked at runtime).
    """
    if settings.USE_SQLITE:
        return "universe_assets"
    return "public.universe_snapshot_v8" if prefer_mv else "public.universe_assets"

