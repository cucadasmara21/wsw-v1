"""
Servicio para operaciones de datos
SQLAlchemy 2.x compatible
"""
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy. orm import Session
from sqlalchemy import func, desc

from models import Asset, Price, RiskMetric


class DataService:
    """Servicio para operaciones de datos"""

    def __init__(self, db: Session):
        self.db = db

    def get_asset(self, asset_id: int) -> Optional[Asset]:
        """Obtener un activo por ID"""
        return self.db.query(Asset).filter(Asset.id == asset_id).first()

    def get_asset_by_symbol(self, symbol: str) -> Optional[Asset]:
        """Obtener un activo por símbolo"""
        return self.db.query(Asset).filter(Asset.symbol == symbol).first()

    def get_assets(
        self,
        skip: int = 0,
        limit: int = 100,
        active_only:  bool = True,
        category:  Optional[str] = None
    ) -> List[Asset]:
        """Obtener lista de activos con paginación"""
        query = self.db.query(Asset)

        if active_only:
            query = query.filter(Asset. is_active == True)

        if category:
            query = query.filter(Asset.category == category)

        return query.order_by(Asset. symbol).offset(skip).limit(limit).all()

    def create_asset(self, asset_data: dict) -> Asset:
        """Crear un nuevo activo"""
        existing = self.get_asset_by_symbol(asset_data. get('symbol', ''))
        if existing: 
            return existing

        db_asset = Asset(**asset_data)
        self.db.add(db_asset)
        self.db.commit()
        self.db.refresh(db_asset)

        return db_asset

    def count_assets(self, active_only: bool = True) -> int:
        """Contar número total de activos"""
        query = self.db.query(func.count(Asset.id))
        if active_only:
            query = query.filter(Asset. is_active == True)
        return query.scalar() or 0

    def get_prices(
        self,
        asset_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[Price]:
        """Obtener precios históricos para un activo"""
        query = self.db.query(Price).filter(Price.asset_id == asset_id)

        if start_date: 
            query = query.filter(Price.time >= start_date)
        if end_date: 
            query = query.filter(Price.time <= end_date)

        return query.order_by(desc(Price.time)).limit(limit).all()

    def get_latest_price(self, asset_id: int) -> Optional[Price]:
        """Obtener el precio más reciente para un activo"""
        return self.db.query(Price).filter(
            Price.asset_id == asset_id
        ).order_by(desc(Price.time)).first()

    def count_prices(self) -> int:
        """Contar número total de precios"""
        return self.db.query(func.count(Price.time)).scalar() or 0

    def get_risk_metrics_history(
        self,
        asset_id: int,
        metric_name: str,
        days: int = 30
    ) -> List[tuple]:
        """Obtener historial de una métrica específica"""
        start_date = datetime.utcnow() - timedelta(days=days)

        metrics = self.db.query(RiskMetric. time, RiskMetric.metric_value).filter(
            RiskMetric.asset_id == asset_id,
            RiskMetric. metric_name == metric_name,
            RiskMetric.time >= start_date
        ).order_by(RiskMetric. time).all()

        return [(m[0], m[1]) for m in metrics]