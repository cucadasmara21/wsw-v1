"""
Paquete de routers API
"""

# Minimal api package to satisfy imports in `main.py`.
# Each module exports an APIRouter named `router`.
from . import assets, risk, scenarios, auth, market

# Export routers for convenience
__all__ = ["assets", "risk", "scenarios", "auth", "market"]
