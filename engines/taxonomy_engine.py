"""
Taxonomy Engine: Converts Category/Asset metadata to bitmask encoding.
Integrates with existing Group/Subgroup/Category hierarchy.
"""
from typing import Optional, List, Dict
import numpy as np
from sqlalchemy.orm import Session
from models import Asset, Category, RiskSnapshot
from engines.bitmask_encoder import pack_taxonomy_mask, pack_batch


# Domain mapping: Category → Domain (0-5)
# Based on "Rule of Six Domains" from documentation
DOMAIN_MAPPING = {
    # Credit & Liquidity Risk (Domain 0)
    'credit': 0,
    'liquidity': 0,
    'banking': 0,
    'corporate_debt': 0,
    
    # Market & Valuation Risk (Domain 1)
    'market': 1,
    'valuation': 1,
    'price': 1,
    'fx': 1,
    'commodity': 1,
    
    # Operational & Technological Risk (Domain 2)
    'operational': 2,
    'tech': 2,
    'cyber': 2,
    'infrastructure': 2,
    
    # Systemic & Interconnected Risk (Domain 3)
    'systemic': 3,
    'interconnected': 3,
    'contagion': 3,
    'shadow_banking': 3,
    
    # Geopolitical & Regulatory Risk (Domain 4)
    'geopolitical': 4,
    'regulatory': 4,
    'sovereign': 4,
    'sanctions': 4,
    
    # Environmental & Transition Risk (Domain 5)
    'environmental': 5,
    'climate': 5,
    'transition': 5,
    'esg': 5,
}


def infer_domain_from_category(category_name: str) -> int:
    """
    Infer domain (0-5) from category name using keyword matching.
    Falls back to domain 0 (Credit & Liquidity) if no match.
    """
    category_lower = category_name.lower()
    
    for keyword, domain_id in DOMAIN_MAPPING.items():
        if keyword in category_lower:
            return domain_id
    
    # Default to Credit & Liquidity Risk
    return 0


def compute_outlier_flag(asset: Asset, risk_snapshot: Optional[RiskSnapshot] = None) -> int:
    """
    Determine if an asset is an outlier based on risk metrics.
    
    Heuristic: outlier if CRI > 80 or any risk component > 0.9
    """
    if risk_snapshot is None:
        return 0
    
    if risk_snapshot.cri and risk_snapshot.cri > 80.0:
        return 1
    
    # Check individual risk components
    risk_components = [
        risk_snapshot.price_risk,
        risk_snapshot.liq_risk,
        risk_snapshot.fund_risk,
        risk_snapshot.cp_risk,
        risk_snapshot.regime_risk,
    ]
    
    if any(r and r > 0.9 for r in risk_components):
        return 1
    
    return 0


def compute_risk01(risk_snapshot: Optional[RiskSnapshot]) -> float:
    """
    Normalize CRI (0-100) to risk01 (0.0-1.0).
    Falls back to 0.0 if no snapshot available.
    """
    if risk_snapshot is None or risk_snapshot.cri is None:
        return 0.0
    
    return np.clip(risk_snapshot.cri / 100.0, 0.0, 1.0)


class TaxonomyEngine:
    """
    Engine for converting assets to taxonomy bitmasks.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def classify_asset(self, asset_id: int) -> np.uint32:
        """
        Classify a single asset and return its bitmask.
        
        Args:
            asset_id: Asset ID
        
        Returns:
            32-bit taxonomy bitmask
        """
        asset = self.db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            raise ValueError(f"Asset {asset_id} not found")
        
        # Infer domain from category
        domain = 0  # default
        if asset.category_id:
            category = self.db.query(Category).filter(Category.id == asset.category_id).first()
            if category:
                domain = infer_domain_from_category(category.name)
        
        # Get latest risk snapshot
        risk_snapshot = (
            self.db.query(RiskSnapshot)
            .filter(RiskSnapshot.asset_id == asset_id)
            .order_by(RiskSnapshot.ts.desc())
            .first()
        )
        
        # Compute components
        outlier = compute_outlier_flag(asset, risk_snapshot)
        risk01 = compute_risk01(risk_snapshot)
        
        # Pack bitmask
        return pack_taxonomy_mask(domain, outlier, risk01)
    
    def classify_batch(self, asset_ids: List[int]) -> np.ndarray:
        """
        Classify multiple assets in batch.
        
        Args:
            asset_ids: List of asset IDs
        
        Returns:
            (N,) array of uint32 bitmasks
        """
        n = len(asset_ids)
        domains = np.zeros(n, dtype=np.int32)
        outliers = np.zeros(n, dtype=np.int32)
        risks01 = np.zeros(n, dtype=np.float32)
        
        # Load assets and risk snapshots in batch
        assets = (
            self.db.query(Asset)
            .filter(Asset.id.in_(asset_ids))
            .all()
        )
        
        asset_map = {a.id: a for a in assets}
        
        # Get latest risk snapshots per asset
        risk_snapshots = (
            self.db.query(RiskSnapshot)
            .filter(RiskSnapshot.asset_id.in_(asset_ids))
            .order_by(RiskSnapshot.ts.desc())
            .all()
        )
        
        # Group by asset_id (keep latest)
        risk_map = {}
        for rs in risk_snapshots:
            if rs.asset_id not in risk_map:
                risk_map[rs.asset_id] = rs
        
        # Process each asset
        for i, asset_id in enumerate(asset_ids):
            asset = asset_map.get(asset_id)
            if not asset:
                continue
            
            # Infer domain
            domain = 0
            if asset.category_id:
                category = self.db.query(Category).filter(Category.id == asset.category_id).first()
                if category:
                    domain = infer_domain_from_category(category.name)
            
            domains[i] = domain
            
            # Get risk snapshot
            risk_snapshot = risk_map.get(asset_id)
            outliers[i] = compute_outlier_flag(asset, risk_snapshot)
            risks01[i] = compute_risk01(risk_snapshot)
        
        # Pack batch
        return pack_batch(domains, outliers, risks01)
