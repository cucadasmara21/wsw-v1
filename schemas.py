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


class RiskOverviewResponse(BaseModel):
    asset_id: int
    symbol: str
    current_price: Optional[float] = None
    cri:  Optional[float] = None
    risk_level: str
    last_updated: datetime