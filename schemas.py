from __future__ import annotations

"""
Esquemas Pydantic para validación y serialización
SQLAlchemy 2.x compatible
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class AssetBase(BaseModel):
    symbol: str
    name: Optional[str] = None
    sector: Optional[str] = None
    category: Optional[str] = None
    exchange: Optional[str] = None
    country: Optional[str] = None


class AssetCreate(AssetBase):
    pass


class AssetUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


class Asset(AssetBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PriceBase(BaseModel):
    time: datetime
    asset_id: int
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: float
    volume: Optional[int] = None


class PriceCreate(PriceBase):
    pass


class Price(PriceBase):
    class Config:
        from_attributes = True


class RiskMetric(BaseModel):
    time: datetime
    asset_id: int
    metric_name: str
    metric_value: float
    calculation_version: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class Alert(BaseModel):
    id: int
    asset_id: int
    alert_type: str
    severity: str
    description:  str
    triggered_at: datetime
    resolved_at: Optional[datetime] = None
    is_resolved: bool

    class Config:
        from_attributes = True


class UserBase(BaseModel):
    email: str
    username: str
    full_name: Optional[str] = None
    role: str = "retail"


class UserCreate(UserBase):
    password: str


class User(UserBase):
    id: int
    is_active: bool
    created_at:  datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str
    refresh_token: Optional[str] = None


class RiskVector(BaseModel):
    price_risk: float
    fundamental_risk: float
    liquidity_risk: float
    counterparty_risk: float
    regime_risk: float


class TopAsset(BaseModel):
    asset_id: str
    asset_name: str
    group_name: str
    subgroup_name: str
    category_name: str
    cri: float
    risk_vector: RiskVector


class GroupAgg(BaseModel):
    group_name: str
    count: int
    cri_avg: float
    vector_avg: RiskVector


class RiskOverviewResponse(BaseModel):
    as_of: str
    universe: int
    cri_avg: float
    vector_avg: RiskVector
    top_assets: List[TopAsset]
    by_group: List[GroupAgg]


class RiskSummaryResponse(BaseModel):
    as_of: str
    universe: int
    cri_avg: float
    vector_avg: RiskVector
    top_risks: Dict[str, List[TopAsset]]  # keys: price_risk, fundamental_risk, liquidity_risk, counterparty_risk, regime_risk


class RiskSnapshotOut(BaseModel):
    id: int
    ts: str
    asset_id: str
    asset_name: str
    group_name: str
    subgroup_name: str
    category_name: str
    price_risk: float
    fundamental_risk: float
    liquidity_risk: float
    counterparty_risk: float
    regime_risk: float
    cri: float


class RiskSeriesPointOut(BaseModel):
    ts: str
    cri: float
    price_risk: float
    fundamental_risk: float
    liquidity_risk: float
    counterparty_risk: float
    regime_risk: float
    # schemas.py
from datetime import datetime
from pydantic import BaseModel


class RiskSnapshotOut(BaseModel):
    ts: datetime
    price_risk: float
    liq_risk: float
    fund_risk: float
    cp_risk: float
    regime_risk: float
    cri: float
    model_version: str


class AssetOut(BaseModel):
    id: int
    symbol: str
    name: str
    asset_type: str
    category_id: int


class AssetDetailOut(AssetOut):
    latest: RiskSnapshotOut | None = None


class PagedAssetsOut(BaseModel):
    total: int
    items: list[AssetOut]


class RiskSummaryRow(BaseModel):
    level: str  # group|subgroup|category
    id: int
    name: str
    parent_id: int | None = None
    avg_cri: float
    avg_price_risk: float
    avg_liq_risk: float
    avg_fund_risk: float
    avg_cp_risk: float
    avg_regime_risk: float
    n_assets: int
