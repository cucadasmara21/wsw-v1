from __future__ import annotations

"""
Modelos SQLAlchemy unificados
Compatible con SQLAlchemy 2.x
SCHEMA UNIFICADO: prices(time, asset_id, close, ...)
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, BigInteger, JSON, Index
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
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True, index=True)
    exchange = Column(String(50))
    country = Column(String(50))
    currency = Column(String(3), default="USD")
    is_active = Column(Boolean, default=True)
    metadata_ = Column('metadata', JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    category_rel = relationship("Category", back_populates="assets")
    prices = relationship("Price", back_populates="asset", cascade="all, delete-orphan")
    risk_metrics = relationship("RiskMetric", back_populates="asset", cascade="all, delete-orphan")
    # Compatibility: keep risk_snapshots relationship expected by other modules
    risk_snapshots = relationship("RiskSnapshot", back_populates="asset", cascade="all, delete-orphan")
    metric_snapshots = relationship("AssetMetricSnapshot", back_populates="asset", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="asset", cascade="all, delete-orphan")

    def to_dict(self):
        """Convertir a diccionario para serialización"""
        return {
            "id": self.id,
            "symbol": self.symbol,
            "name": self.name,
            "sector": self.sector,
            "category_id": self.category_id,
            "exchange": self.exchange,
            "country": self.country,
            "currency": self.currency,
            "is_active": self.is_active,
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
    asset_id = Column(Integer, ForeignKey("assets.id"), primary_key=True)
    metric_name = Column(String(50), primary_key=True)
    metric_value = Column(Float(precision=12, decimal_return_scale=6))
    calculation_version = Column(String(20))
    metadata_ = Column('metadata', JSON, default=dict)

    asset = relationship("Asset", back_populates="risk_metrics")


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
    # models.py

# (comentarios opcionales)
"""docstring opcional"""

from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    String, Integer, Float, DateTime, ForeignKey, Index, BigInteger
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)

    subgroups: Mapped[List["Subgroup"]] = relationship(back_populates="group", cascade="all, delete-orphan")


class Subgroup(Base):
    __tablename__ = "subgroups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)

    group: Mapped["Group"] = relationship(back_populates="subgroups")
    categories: Mapped[List["Category"]] = relationship(back_populates="subgroup", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_subgroups_group_name", "group_id", "name", unique=True),
    )


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subgroup_id: Mapped[int] = mapped_column(ForeignKey("subgroups.id"), index=True)
    name: Mapped[str] = mapped_column(String(140), index=True)

    subgroup: Mapped["Subgroup"] = relationship(back_populates="categories")
    assets: Mapped[List["Asset"]] = relationship("Asset", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_categories_subgroup_name", "subgroup_id", "name", unique=True),
    )


class RiskSnapshot(Base):
    __tablename__ = "risk_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)

    ts: Mapped[datetime] = mapped_column(DateTime, index=True)

    price_risk: Mapped[float] = mapped_column(Float)
    liq_risk: Mapped[float] = mapped_column(Float)
    fund_risk: Mapped[float] = mapped_column(Float)
    cp_risk: Mapped[float] = mapped_column(Float)
    regime_risk: Mapped[float] = mapped_column(Float)

    cri: Mapped[float] = mapped_column(Float, index=True)
    model_version: Mapped[str] = mapped_column(String(32), default="mvp-0.1")

    asset: Mapped["Asset"] = relationship(back_populates="risk_snapshots")

    __table_args__ = (
        Index("ix_risk_asset_ts", "asset_id", "ts"),
    )


class PriceBar(Base):
    """Precio OHLCV básico por símbolo y timestamp."""

    __tablename__ = "price_bars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int | None] = mapped_column(BigInteger)
    source: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("uq_price_bars_symbol_ts", "symbol", "ts", unique=True),
    )


class IndicatorSnapshot(Base):
    """Snapshot de indicadores calculados (SMA, RSI, riesgo)."""

    __tablename__ = "indicator_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), default="1d", nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    sma_20: Mapped[float | None] = mapped_column(Float)
    rsi_14: Mapped[float | None] = mapped_column(Float)
    risk_v0: Mapped[float | None] = mapped_column(Float)
    explain_json: Mapped[dict | None] = mapped_column(JSON)
    snapshot_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_indicator_snapshot_symbol_tf_ts", "symbol", "timeframe", "ts", unique=True),
    )

class AssetMetricSnapshot(Base):
    """Snapshots de métricas calculadas por activo (legacy)"""
    __tablename__ = "asset_metric_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True, nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    
    # Metrics payload (all metrics computed for this asset)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)
    
    # Quality indicators
    quality: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # Explanation/breakdown
    explain: Mapped[dict] = mapped_column(JSON, default=dict)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    asset: Mapped["Asset"] = relationship(back_populates="metric_snapshots")

    __table_args__ = (
        Index("ix_metric_snapshot_asset_as_of", "asset_id", "as_of", unique=True),
    )


class MetricSnapshot(Base):
    """Metric snapshots con score y explain"""
    __tablename__ = "metric_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True, nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)

    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)
    score: Mapped[float] = mapped_column(Float, index=True)
    explain: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_metric_snapshots_asset_as_of", "asset_id", "as_of", unique=True),
    )


class Alert(Base):
    """Alertas generadas basadas en métricas"""
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True, nullable=False)
    
    key: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g., "rsi_high", "drawdown_alert"
    severity: Mapped[str] = mapped_column(String(20), default="warning")  # info, warning, critical
    message: Mapped[str] = mapped_column(String(500))
    
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    payload: Mapped[dict] = mapped_column(JSON, default=dict)  # Context data

    asset: Mapped["Asset"] = relationship(back_populates="alerts")

    __table_args__ = (
        Index("ix_alerts_asset_triggered", "asset_id", "triggered_at"),
        Index("ix_alerts_severity", "severity"),
    )


class CategoryAsset(Base):
    """Association table for dynamic category selection with scoring"""
    __tablename__ = "category_assets"

    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), primary_key=True, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), primary_key=True, index=True)
    
    is_candidate: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    
    last_score: Mapped[float | None] = mapped_column(Float)
    last_rank: Mapped[int | None] = mapped_column(Integer)
    score_ema: Mapped[float | None] = mapped_column(Float)  # Exponential moving average for stability
    
    last_selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_category_assets_category_selected", "category_id", "is_selected"),
        Index("ix_category_assets_score", "category_id", "last_score"),
    )


class SelectionRun(Base):
    """Record of dynamic selection algorithm execution"""
    __tablename__ = "selection_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    top_n: Mapped[int] = mapped_column(Integer, nullable=False)
    lookback_days: Mapped[int] = mapped_column(Integer, nullable=False)
    
    weights_json: Mapped[dict] = mapped_column(JSON, default=dict)  # Algorithm weights/params
    notes: Mapped[str | None] = mapped_column(String(500))
    
    results_json: Mapped[dict] = mapped_column(JSON, default=dict)  # Selected assets with scores/explain

    __table_args__ = (
        Index("ix_selection_runs_category_created", "category_id", "created_at"),
    )