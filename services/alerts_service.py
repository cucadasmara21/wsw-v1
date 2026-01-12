"""
Alerts generation service based on metrics
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from models import Asset, Alert


class AlertsService:
    """Generate and manage alerts based on computed metrics"""
    
    @staticmethod
    def generate_alerts(
        asset: Asset,
        metrics: Dict[str, Any],
        quality: Dict[str, Any],
        db: Optional[Session] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate alerts based on metrics and quality indicators.
        
        Returns list of alert dicts ready to be saved
        """
        alerts_to_create = []
        
        # RSI alerts
        rsi = metrics.get("rsi14")
        if rsi is not None:
            if rsi > 70:
                alerts_to_create.append({
                    "key": "rsi_high",
                    "severity": "warning",
                    "message": f"RSI14 is high ({rsi:.1f})",
                    "payload": {"rsi": rsi}
                })
            elif rsi < 30:
                alerts_to_create.append({
                    "key": "rsi_low",
                    "severity": "warning",
                    "message": f"RSI14 is low ({rsi:.1f})",
                    "payload": {"rsi": rsi}
                })
        
        # Drawdown alerts
        max_dd = metrics.get("max_drawdown")
        if max_dd is not None and max_dd < -0.15:
            alerts_to_create.append({
                "key": "drawdown_alert",
                "severity": "critical",
                "message": f"Large drawdown ({max_dd*100:.1f}%)",
                "payload": {"max_drawdown": max_dd}
            })
        
        # Volatility alerts
        volatility = metrics.get("volatility")
        if volatility is not None and volatility > 0.05:
            alerts_to_create.append({
                "key": "high_volatility",
                "severity": "info",
                "message": f"High volatility ({volatility*100:.1f}%)",
                "payload": {"volatility": volatility}
            })
        
        # Data quality alerts
        if quality.get("low_data"):
            alerts_to_create.append({
                "key": "low_data",
                "severity": "warning",
                "message": f"Insufficient data ({quality.get('bars_count', 0)} bars)",
                "payload": quality
            })
        
        # If db session provided, save alerts
        if db:
            AlertsService.save_alerts(asset, alerts_to_create, db)
        
        return alerts_to_create
    
    @staticmethod
    def save_alerts(asset: Asset, alerts_data: List[Dict[str, Any]], db: Session):
        """Save alerts to database, avoiding duplicates"""
        for alert_data in alerts_data:
            # Check if alert already exists and is not resolved
            existing = db.query(Alert).filter(
                Alert.asset_id == asset.id,
                Alert.key == alert_data["key"],
                Alert.resolved_at == None
            ).first()
            
            if not existing:
                alert = Alert(
                    asset_id=asset.id,
                    **alert_data
                )
                db.add(alert)
        
        db.commit()
    
    @staticmethod
    def resolve_alert(alert_id: int, db: Session):
        """Mark alert as resolved"""
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if alert:
            alert.resolved_at = datetime.utcnow()
            db.commit()
        return alert
