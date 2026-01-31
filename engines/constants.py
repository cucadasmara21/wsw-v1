"""
P-03: Deterministic real-time budget constants.
Shared so tests can assert without importing heavy deps (redis, asyncpg).
"""
WORK_CAP_PER_TICK = 50_000
