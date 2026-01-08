"""
Script de ingesta de datos (yfinance) — tolerante a dependencias opcionales
SQLAlchemy 2.x compatible
"""
import logging
from datetime import datetime, timedelta

# Inicializar logger temprano para que los mensajes de import fallido no causen NameError
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# yfinance and pandas are optional analytics dependencies; allow running the app without them.
try:
    import yfinance as yf
    import pandas as pd
except ModuleNotFoundError:
    yf = None
    pd = None
    logger.warning("⚠️  analytics deps not installed: ingest disabled. Install `pip install -r requirements-analytics.txt` to enable.")

from database import SessionLocal
from models import Asset, Price
from config import settings


def ingest_data():
    """Ingesta de datos de ejemplo"""
    if yf is None or pd is None:
        logger.error("❌ yfinance/pandas not installed. Install `requirements-analytics.txt` to use ingest.")
        return

    tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'SPY', 'QQQ']
    logger.info(f"Iniciando ingesta para: {tickers}")

    db = SessionLocal()

    try:
        for ticker in tickers:
            logger.info(f"Procesando {ticker}...")

            # Crear o obtener activo
            asset = db.query(Asset).filter(Asset.symbol == ticker).first()
            if not asset:
                asset = Asset(symbol=ticker, name=ticker, is_active=True)
                db.add(asset)
                db.commit()
                db.refresh(asset)

            try:
                end_date = datetime.utcnow()
                start_date = end_date - timedelta(days=90)

                df = yf.download(
                    ticker,
                    start=start_date,
                    end=end_date,
                    progress=False,
                    auto_adjust=True
                )

                if df.empty:
                    logger.warning(f"No hay datos para {ticker}")
                    continue

                df = df.reset_index()

                for _, row in df.iterrows():
                    price = Price(
                        time=pd.Timestamp(row['Date']).to_pydatetime(),
                        asset_id=asset.id,
                        open=float(row['Open']) if pd.notna(row['Open']) else None,
                        high=float(row['High']) if pd.notna(row['High']) else None,
                        low=float(row['Low']) if pd.notna(row['Low']) else None,
                        close=float(row['Close']),
                        volume=int(row['Volume']) if pd.notna(row['Volume']) else None
                    )
                    db.add(price)

                db.commit()
                logger.info(f"✅ {ticker}:  {len(df)} registros insertados")

            except Exception as e:
                logger.error(f"❌ Error {ticker}: {e}")
                db.rollback()

    finally:
        db.close()
        logger.info("✅ Ingesta completada")


if __name__ == "__main__": 
    ingest_data()