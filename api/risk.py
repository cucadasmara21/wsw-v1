from __future__ import annotations

"""
Endpoints para métricas de riesgo
SQLAlchemy 2.x compatible
"""
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db, engine
from models import Asset, RiskMetric, Price
from schemas import RiskOverviewResponse, RiskSnapshotOut, RiskSeriesPointOut, RiskSummaryResponse, TopAsset
from services.risk_service import compute_risk_vector, compute_cri
from services.rbac_service import require_role
from schemas import User

router = APIRouter(tags=["risk"])


# ============================================================================
# BLOCK 10: Risk Engine v1 Endpoints (Real-time CRI computation)
# ============================================================================

@router.get("/top")
def get_risk_top(
    limit: int = Query(10, ge=1, le=100),
    lookback_days: int = Query(90, ge=1, le=365),
    scope: str = Query("universe", regex="^(universe|selection)$"),
    db: Session = Depends(get_db),
):
    """
    Get top risk assets by CRI (real-time computation).
    
    - scope=universe: all active assets
    - scope=selection: selected assets (placeholder; same as universe for now)
    - Returns: sorted by CRI descending
    """
    
    # Query active assets
    assets = db.query(Asset).filter(Asset.active == True).all()
    
    if not assets:
        return []
    
    # Compute risk for each
    risk_data = []
    for asset in assets:
        # Fetch recent prices
        prices_query = (
            db.query(Price)
            .filter(Price.asset_id == asset.id)
            .order_by(Price.time.desc())
            .limit(lookback_days)
            .all()
        )
        
        if not prices_query or len(prices_query) < 2:
            continue  # Skip assets with insufficient data
        
        # Sort chronologically (oldest first)
        prices_query.reverse()
        
        prices = [float(p.close) for p in prices_query]
        volumes = [float(p.volume) if p.volume else 0.0 for p in prices_query]
        
        # Compute risk
        risk_vector = compute_risk_vector(prices, volumes, lookback_days)
        cri = compute_cri(risk_vector)
        
        if cri is not None:
            # Aggregate data_meta from latest price
            data_meta = {}
            if prices_query:
                latest = prices_query[-1]
                if hasattr(latest, "data_meta") and latest.data_meta:
                    data_meta = latest.data_meta.copy() if isinstance(latest.data_meta, dict) else {}
            
            data_meta["insufficient_data"] = risk_vector.get("insufficient_data", False)
            
            risk_data.append({
                "asset_id": asset.id,
                "symbol": asset.symbol,
                "name": asset.name or "N/A",
                "cri": cri,
                "risk_vector": risk_vector,
                "data_meta": data_meta,
            })
    
    # Sort by CRI descending
    risk_data.sort(key=lambda r: r["cri"], reverse=True)
    
    # Return top N with ranks
    result = []
    for i, risk in enumerate(risk_data[:limit]):
        risk_copy = risk.copy()
        risk_copy["rank"] = i + 1
        result.append(risk_copy)
    
    return result


@router.get("/assets/{asset_id}")
def get_risk_asset(
    asset_id: int,
    lookback_days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """
    Get risk details for a specific asset (real-time computation).
    
    Returns: {asset_id, symbol, name, cri, risk_vector, data_meta}
    """
    
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Fetch recent prices
    prices_query = (
        db.query(Price)
        .filter(Price.asset_id == asset_id)
        .order_by(Price.time.desc())
        .limit(lookback_days)
        .all()
    )
    
    if not prices_query or len(prices_query) < 2:
        return {
            "asset_id": asset_id,
            "symbol": asset.symbol,
            "name": asset.name or "N/A",
            "cri": None,
            "risk_vector": {},
            "data_meta": {"insufficient_data": True},
        }
    
    # Sort chronologically (oldest first)
    prices_query.reverse()
    
    prices = [float(p.close) for p in prices_query]
    volumes = [float(p.volume) if p.volume else 0.0 for p in prices_query]
    
    # Compute risk
    risk_vector = compute_risk_vector(prices, volumes, lookback_days)
    cri = compute_cri(risk_vector)
    
    # Aggregate data_meta from latest price
    data_meta = {}
    if prices_query:
        latest = prices_query[-1]
        if hasattr(latest, "data_meta") and latest.data_meta:
            data_meta = latest.data_meta.copy() if isinstance(latest.data_meta, dict) else {}
    
    data_meta["insufficient_data"] = risk_vector.get("insufficient_data", False)
    
    return {
        "asset_id": asset_id,
        "symbol": asset.symbol,
        "name": asset.name or "N/A",
        "cri": cri,
        "risk_vector": risk_vector,
        "data_meta": data_meta,
    }


@router.post("/recompute")
def recompute_risk(
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Recompute risk for all assets (admin only).
    
    Returns: {computed_count, assets_with_data, assets_insufficient}
    """
    
    assets = db.query(Asset).filter(Asset.active == True).limit(limit).all()
    
    computed_count = 0
    assets_with_data = 0
    assets_insufficient = 0
    
    for asset in assets:
        prices_query = (
            db.query(Price)
            .filter(Price.asset_id == asset.id)
            .order_by(Price.time.desc())
            .limit(90)
            .all()
        )
        
        if prices_query and len(prices_query) >= 2:
            prices_query.reverse()
            prices = [float(p.close) for p in prices_query]
            volumes = [float(p.volume) if p.volume else 0.0 for p in prices_query]
            
            risk_vector = compute_risk_vector(prices, volumes, 90)
            cri = compute_cri(risk_vector)
            
            if cri is not None:
                assets_with_data += 1
            else:
                assets_insufficient += 1
        else:
            assets_insufficient += 1
        
        computed_count += 1
    
    return {
        "status": "recomputed",
        "computed_count": computed_count,
        "assets_with_data": assets_with_data,
        "assets_insufficient": assets_insufficient,
    }


# ============================================================================
# Legacy endpoints (existing risk snapshots functionality)
# ============================================================================

@router.get("/overview", response_model=RiskOverviewResponse)
def get_risk_overview(
    top_n: int = Query(10, ge=1, le=200),
):
    """Return an aggregated risk overview as of the latest snapshot per asset.
    Uses sqlite3 direct queries against the configured DATABASE_URL sqlite file (avoids SQLAlchemy/ORM).
    """
    import sqlite3
    from config import settings
    import logging

    log = logging.getLogger(__name__)

    # Resolve SQLite file path from DATABASE_URL
    db_url = settings.DATABASE_URL
    if 'sqlite' not in db_url.lower():
        raise HTTPException(status_code=500, detail="Risk overview requires a sqlite DATABASE_URL")

    # support sqlite:///./wsw.db or sqlite:///<abs>
    db_path = db_url.split('sqlite:///')[-1]
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # as_of
        cur.execute('SELECT MAX(ts) as max_ts FROM risk_snapshots')
        row = cur.fetchone()
        as_of = row['max_ts'] if row else None
        if as_of is None:
            raise HTTPException(status_code=200, detail={"as_of": None, "universe": 0, "cri_avg": 0.0, "vector_avg": {"price_risk":0.0,"fundamental_risk":0.0,"liquidity_risk":0.0,"counterparty_risk":0.0,"regime_risk":0.0}, "top_assets": [], "by_group": []})

        # universe and vector averages
        cur.execute('''
            SELECT COUNT(*) as cnt,
                   AVG(COALESCE(price_risk,0)) as avg_price,
                   AVG(COALESCE(fundamental_risk,0)) as avg_fund,
                   AVG(COALESCE(liquidity_risk,0)) as avg_liq,
                   AVG(COALESCE(counterparty_risk,0)) as avg_cp,
                   AVG(COALESCE(regime_risk,0)) as avg_regime,
                   AVG(COALESCE(cri,0)) as avg_cri
            FROM risk_snapshots
            WHERE ts = ?
        ''', (as_of,))
        agg = cur.fetchone()
        universe = int(agg['cnt'] or 0)
        vector_avg = {
            'price_risk': float(agg['avg_price'] or 0.0),
            'fundamental_risk': float(agg['avg_fund'] or 0.0),
            'liquidity_risk': float(agg['avg_liq'] or 0.0),
            'counterparty_risk': float(agg['avg_cp'] or 0.0),
            'regime_risk': float(agg['avg_regime'] or 0.0),
        }
        cri_avg = float(agg['avg_cri'] or 0.0)

        # top assets
        cur.execute('''
            SELECT asset_id, asset_name, group_name, subgroup_name, category_name, cri, price_risk, fundamental_risk, liquidity_risk, counterparty_risk, regime_risk
            FROM risk_snapshots
            WHERE ts = ?
            ORDER BY cri DESC
            LIMIT ?
        ''', (as_of, top_n))
        tops = []
        for r in cur.fetchall():
            tops.append({
                'asset_id': str(r['asset_id']),
                'asset_name': r['asset_name'],
                'group_name': r['group_name'] or '',
                'subgroup_name': r['subgroup_name'] or '',
                'category_name': r['category_name'] or '',
                'cri': float(r['cri'] or 0.0),
                'risk_vector': {
                    'price_risk': float(r['price_risk'] or 0.0),
                    'fundamental_risk': float(r['fundamental_risk'] or 0.0),
                    'liquidity_risk': float(r['liquidity_risk'] or 0.0),
                    'counterparty_risk': float(r['counterparty_risk'] or 0.0),
                    'regime_risk': float(r['regime_risk'] or 0.0),
                }
            })

        # by_group
        cur.execute('''
            SELECT group_name as group_name, COUNT(*) as cnt, AVG(COALESCE(cri,0)) as avg_cri,
                   AVG(COALESCE(price_risk,0)) as avg_price, AVG(COALESCE(fundamental_risk,0)) as avg_fund,
                   AVG(COALESCE(liquidity_risk,0)) as avg_liq, AVG(COALESCE(counterparty_risk,0)) as avg_cp,
                   AVG(COALESCE(regime_risk,0)) as avg_regime
            FROM risk_snapshots
            WHERE ts = ?
            GROUP BY group_name
            ORDER BY avg_cri DESC
        ''', (as_of,))
        groups = []
        for r in cur.fetchall():
            groups.append({
                'group_name': r['group_name'] or 'Unknown',
                'count': int(r['cnt'] or 0),
                'cri_avg': float(r['avg_cri'] or 0.0),
                'vector_avg': {
                    'price_risk': float(r['avg_price'] or 0.0),
                    'fundamental_risk': float(r['avg_fund'] or 0.0),
                    'liquidity_risk': float(r['avg_liq'] or 0.0),
                    'counterparty_risk': float(r['avg_cp'] or 0.0),
                    'regime_risk': float(r['avg_regime'] or 0.0),
                }
            })

        resp = {
            'as_of': str(as_of),
            'universe': universe,
            'cri_avg': cri_avg,
            'vector_avg': vector_avg,
            'top_assets': tops,
            'by_group': groups
        }
        return resp
    except HTTPException:
        raise
    except Exception as e:
        log.exception('Error while building risk overview')
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            conn.close()
        except:
            pass


@router.get("/summary_sql", response_model=RiskSummaryResponse)
def risk_summary_sql():
    """Return a summary using raw sqlite3 queries (SQL-only fallback for /summary).
    This avoids SQLAlchemy mapper FK issues by querying `risk_snapshots` directly.
    """
    import sqlite3
    from config import settings
    import logging

    log = logging.getLogger(__name__)
    db_url = settings.DATABASE_URL
    if 'sqlite' not in db_url.lower():
        raise HTTPException(status_code=500, detail="Risk summary SQL requires a sqlite DATABASE_URL")

    db_path = db_url.split('sqlite:///')[-1]
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # as_of
        cur.execute('SELECT MAX(ts) as max_ts FROM risk_snapshots')
        row = cur.fetchone()
        as_of = row['max_ts'] if row else None
        if as_of is None:
            # empty result
            empty_resp = {
                'as_of': None,
                'universe': 0,
                'cri_avg': 0.0,
                'vector_avg': {'price_risk':0.0,'fundamental_risk':0.0,'liquidity_risk':0.0,'counterparty_risk':0.0,'regime_risk':0.0},
                'top_risks': {k: [] for k in ['price_risk','fundamental_risk','liquidity_risk','counterparty_risk','regime_risk']}
            }
            return empty_resp

        # universe + averages
        cur.execute('''
            SELECT COUNT(*) as cnt,
                   AVG(COALESCE(price_risk,0)) as avg_price,
                   AVG(COALESCE(fundamental_risk,0)) as avg_fund,
                   AVG(COALESCE(liquidity_risk,0)) as avg_liq,
                   AVG(COALESCE(counterparty_risk,0)) as avg_cp,
                   AVG(COALESCE(regime_risk,0)) as avg_regime,
                   AVG(COALESCE(cri,0)) as avg_cri
            FROM risk_snapshots
            WHERE ts = ?
        ''', (as_of,))
        agg = cur.fetchone()
        universe = int(agg['cnt'] or 0)
        vector_avg = {
            'price_risk': float(agg['avg_price'] or 0.0),
            'fundamental_risk': float(agg['avg_fund'] or 0.0),
            'liquidity_risk': float(agg['avg_liq'] or 0.0),
            'counterparty_risk': float(agg['avg_cp'] or 0.0),
            'regime_risk': float(agg['avg_regime'] or 0.0),
        }
        cri_avg = float(agg['avg_cri'] or 0.0)

        risk_keys = ['price_risk','fundamental_risk','liquidity_risk','counterparty_risk','regime_risk']
        top_risks: dict = {}

        for rk in risk_keys:
            q = f"""
                SELECT asset_id, asset_name, group_name, subgroup_name, category_name, cri, price_risk, fundamental_risk, liquidity_risk, counterparty_risk, regime_risk
                FROM risk_snapshots
                WHERE ts = ?
                ORDER BY {rk} DESC
                LIMIT 5
            """
            cur.execute(q, (as_of,))
            rows = cur.fetchall()
            lst = []
            for r in rows:
                lst.append({
                    'asset_id': str(r['asset_id']),
                    'asset_name': r['asset_name'],
                    'group_name': r['group_name'] or '',
                    'subgroup_name': r['subgroup_name'] or '',
                    'category_name': r['category_name'] or '',
                    'cri': float(r['cri'] or 0.0),
                    'risk_vector': {
                        'price_risk': float(r['price_risk'] or 0.0),
                        'fundamental_risk': float(r['fundamental_risk'] or 0.0),
                        'liquidity_risk': float(r['liquidity_risk'] or 0.0),
                        'counterparty_risk': float(r['counterparty_risk'] or 0.0),
                        'regime_risk': float(r['regime_risk'] or 0.0),
                    }
                })
            top_risks[rk] = lst

        resp = {
            'as_of': str(as_of),
            'universe': universe,
            'cri_avg': cri_avg,
            'vector_avg': vector_avg,
            'top_risks': top_risks,
        }
        return resp
    except HTTPException:
        raise
    except Exception as e:
        log.exception('Error while building risk summary sql')
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            conn.close()
        except:
            pass


@router.get("/timeseries/{asset_id}", response_model=List[RiskSeriesPointOut])
def get_risk_timeseries(
    asset_id: str,
    days: int = Query(30, ge=1, le=365),
):
    try:
        start = datetime.utcnow() - timedelta(days=days)
        start_iso = start.isoformat()
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT ts, cri, price_risk, fundamental_risk, liquidity_risk, counterparty_risk, regime_risk
                FROM risk_snapshots
                WHERE asset_id = :asset_id AND ts >= :start
                ORDER BY ts ASC
            """), {"asset_id": asset_id, "start": start_iso}).mappings().all()
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/asset/{asset_id}")
async def get_asset_risk(
    asset_id: int,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db)
):
    """Obtener métricas de riesgo para un activo específico"""
    try:
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            raise HTTPException(status_code=404, detail="Asset not found")

        start_date = datetime.utcnow() - timedelta(days=days)
        metrics = db.query(RiskMetric).filter(
            RiskMetric.asset_id == asset_id,
            RiskMetric.time >= start_date
        ).order_by(RiskMetric.time).all()

        return {
            "asset":  asset.to_dict(),
            "metrics": [
                {
                    "time": m.time,
                    "metric_name": m.metric_name,
                    "metric_value": m.metric_value
                }
                for m in metrics
            ],
            "last_updated": datetime.utcnow().isoformat()
        }
    except Exception as e: 
        raise HTTPException(status_code=500, detail=str(e))
    # api/risks.py

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, select

from database import get_db
# Use raw SQL in this module for summary/top to avoid mapper FK inference issues
from models import Asset
from schemas import RiskSummaryRow

# use module-level `router` (registered in main.py with prefix `/api/risk`)

# Detect known schema issues (e.g., missing FK relationships) early and expose readable error
_schema_ok = True
_schema_err = None
try:
    # probing Category.assets will force SQLAlchemy to configure related mappers and surface FK issues
    from models import Category as _Category
    _ = getattr(_Category, 'assets', None)
except Exception as e:
    _schema_ok = False
    _schema_err = str(e)


def _latest_snapshots_subq():
    # subquery: latest ts per asset_id
    return (
        select(
            RiskSnapshot.asset_id.label("asset_id"),
            func.max(RiskSnapshot.ts).label("max_ts"),
        )
        .group_by(RiskSnapshot.asset_id)
        .subquery()
    )


@router.get("/summary", response_model=list[RiskSummaryRow])
def risk_summary(
    level: str = Query("category", pattern="^(group|subgroup|category)$"),
    db: Session = Depends(get_db),
):
    """Return aggregated risk rows per group/subgroup/category using SQL joins (avoid ORM relationship inference).
    Uses latest snapshot per asset (max ts).
    """
    if not _schema_ok:
        raise HTTPException(status_code=500, detail=f"Schema configuration issue detected: {_schema_err}")
    try:
        # Use raw SQL to avoid SQLAlchemy mapper FK inference issues in this schema
        if level == "group":
            sql = text("""
                SELECT g.id as id, g.name as name,
                       AVG(rs.cri) as avg_cri,
                       AVG(rs.price_risk) as avg_price_risk,
                       AVG(rs.liq_risk) as avg_liq_risk,
                       AVG(rs.fund_risk) as avg_fund_risk,
                       AVG(rs.cp_risk) as avg_cp_risk,
                       AVG(rs.regime_risk) as avg_regime_risk,
                       COUNT(DISTINCT a.id) as n_assets
                FROM groups g
                JOIN subgroups sg ON sg.group_id = g.id
                JOIN categories c ON c.subgroup_id = sg.id
                JOIN assets a ON a.category = c.name
                JOIN (
                    SELECT rs1.* FROM risk_snapshots rs1
                    JOIN (SELECT asset_id, max(ts) as max_ts FROM risk_snapshots GROUP BY asset_id) lm
                      ON rs1.asset_id = lm.asset_id AND rs1.ts = lm.max_ts
                ) rs ON rs.asset_id = a.id
                GROUP BY g.id, g.name
                ORDER BY avg_cri DESC
            """)
        elif level == "subgroup":
            sql = text("""
                SELECT sg.id as id, sg.name as name, sg.group_id as parent_id,
                       AVG(rs.cri) as avg_cri,
                       AVG(rs.price_risk) as avg_price_risk,
                       AVG(rs.liq_risk) as avg_liq_risk,
                       AVG(rs.fund_risk) as avg_fund_risk,
                       AVG(rs.cp_risk) as avg_cp_risk,
                       AVG(rs.regime_risk) as avg_regime_risk,
                       COUNT(DISTINCT a.id) as n_assets
                FROM subgroups sg
                JOIN categories c ON c.subgroup_id = sg.id
                JOIN assets a ON a.category = c.name
                JOIN (
                    SELECT rs1.* FROM risk_snapshots rs1
                    JOIN (SELECT asset_id, max(ts) as max_ts FROM risk_snapshots GROUP BY asset_id) lm
                      ON rs1.asset_id = lm.asset_id AND rs1.ts = lm.max_ts
                ) rs ON rs.asset_id = a.id
                GROUP BY sg.id, sg.name, sg.group_id
                ORDER BY avg_cri DESC
            """)
        else:
            sql = text("""
                SELECT c.id as id, c.name as name, c.subgroup_id as parent_id,
                       AVG(rs.cri) as avg_cri,
                       AVG(rs.price_risk) as avg_price_risk,
                       AVG(rs.liq_risk) as avg_liq_risk,
                       AVG(rs.fund_risk) as avg_fund_risk,
                       AVG(rs.cp_risk) as avg_cp_risk,
                       AVG(rs.regime_risk) as avg_regime_risk,
                       COUNT(DISTINCT a.id) as n_assets
                FROM categories c
                JOIN assets a ON a.category = c.name
                JOIN (
                    SELECT rs1.* FROM risk_snapshots rs1
                    JOIN (SELECT asset_id, max(ts) as max_ts FROM risk_snapshots GROUP BY asset_id) lm
                      ON rs1.asset_id = lm.asset_id AND rs1.ts = lm.max_ts
                ) rs ON rs.asset_id = a.id
                GROUP BY c.id, c.name, c.subgroup_id
                ORDER BY avg_cri DESC
            """)

        with engine.connect() as conn:
            rows = conn.execute(sql).mappings().all()

        result = []
        for r in rows:
            result.append(
                RiskSummaryRow(
                    level=level,
                    id=int(r['id']),
                    name=r['name'],
                    parent_id=int(r['parent_id']) if r.get('parent_id') is not None else None,
                    avg_cri=float(r['avg_cri'] or 0),
                    avg_price_risk=float(r['avg_price_risk'] or 0),
                    avg_liq_risk=float(r['avg_liq_risk'] or 0),
                    avg_fund_risk=float(r['avg_fund_risk'] or 0),
                    avg_cp_risk=float(r['avg_cp_risk'] or 0),
                    avg_regime_risk=float(r['avg_regime_risk'] or 0),
                    n_assets=int(r['n_assets'] or 0),
                )
            )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/top")
def top_risks(
    limit: int = Query(15, ge=1, le=200),
):
    """Return top assets by latest CRI using raw SQL to avoid mapper FK issues."""
    try:
        sql = text("""
            SELECT a.id, a.symbol, a.name, a.asset_type, a.category as category_id, rs.ts, rs.cri, rs.price_risk, rs.liq_risk, rs.fund_risk, rs.cp_risk, rs.regime_risk
            FROM assets a
            JOIN (
                SELECT rs1.* FROM risk_snapshots rs1
                JOIN (SELECT asset_id, max(ts) as max_ts FROM risk_snapshots GROUP BY asset_id) lm
                  ON rs1.asset_id = lm.asset_id AND rs1.ts = lm.max_ts
            ) rs ON rs.asset_id = a.id
            ORDER BY rs.cri DESC
            LIMIT :limit
        """)
        with engine.connect() as conn:
            rows = conn.execute(sql, {"limit": limit}).mappings().all()
        return [
            {
                "id": int(r['id']),
                "symbol": r['symbol'],
                "name": r['name'],
                "asset_type": r.get('asset_type'),
                "category_id": r.get('category'),
                "ts": str(r.get('ts')),
                "cri": float(r.get('cri') or 0),
                "price_risk": float(r.get('price_risk') or 0),
                "liq_risk": float(r.get('liq_risk') or 0),
                "fund_risk": float(r.get('fund_risk') or 0),
                "cp_risk": float(r.get('cp_risk') or 0),
                "regime_risk": float(r.get('regime_risk') or 0),
            }
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
