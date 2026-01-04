"""
Modelos SQLAlchemy unificados
Compatible con SQLAlchemy 2.x
SCHEMA UNIFICADO: prices(time, asset_id, close, ...)
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, BigInteger, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from database import Base


class Asset(Base):
    """Modelo para activos financieros"""
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), unique=True, index=True, nullable=False)
    name = Column(String(200))
    sector = Column(String(100))
    category = Column(String(100))
    group_name = Column(String(100))
    exchange = Column(String(50))
    country = Column(String(50))
    currency = Column(String(3), default="USD")
    is_active = Column(Boolean, default=True)
    metadata = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    prices = relationship("Price", back_populates="asset", cascade="all, delete-orphan")
    risk_metrics = relationship("RiskMetric", back_populates="asset", cascade="all, delete-orphan")

    def to_dict(self):
        """Convertir a diccionario para serialización"""
        return {
            "id": self.id,
            "symbol": self.symbol,
            "name": self.name,
            "sector": self. sector,
            "category": self.category,
            "exchange": self.exchange,
            "country": self.country,
            "currency": self.currency,
            "is_active": self. is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at":  self.updated_at.isoformat() if self.updated_at else None
        }


class Price(Base):
    """Modelo para precios históricos - SCHEMA UNIFICADO"""
    __tablename__ = "prices"

    time = Column(DateTime(timezone=True), primary_key=True, nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), primary_key=True)
    open = Column(Float(precision=12, decimal_return_scale=4))
    high = Column(Float(precision=12, decimal_return_scale=4))
    low = Column(Float(precision=12, decimal_return_scale=4))
    close = Column(Float(precision=12, decimal_return_scale=4), nullable=False)
    volume = Column(BigInteger)
    dividends = Column(Float(precision=12, decimal_return_scale=4))
    stock_splits = Column(Float(precision=12, decimal_return_scale=4))

    asset = relationship("Asset", back_populates="prices")


class RiskMetric(Base):
    """Modelo para métricas de riesgo calculadas"""
    __tablename__ = "risk_metrics"

    time = Column(DateTime(timezone=True), primary_key=True, nullable=False)
    asset_id = Column(Integer, ForeignKey("assets. id"), primary_key=True)
    metric_name = Column(String(50), primary_key=True)
    metric_value = Column(Float(precision=12, decimal_return_scale=6))
    calculation_version = Column(String(20))
    metadata = Column(JSON, default=dict)

    asset = relationship("Asset", back_populates="risk_metrics")


class Alert(Base):
    """Modelo para alertas generadas"""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"))
    alert_type = Column(String(50))
    severity = Column(String(20))
    description = Column(String(500))
    triggered_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True))
    is_resolved = Column(Boolean, default=False)
    metadata = Column(JSON, default=dict)

    asset = relationship("Asset")


class User(Base):
    """Modelo para usuarios del sistema"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(200))
    role = Column(String(50), default="retail")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True))