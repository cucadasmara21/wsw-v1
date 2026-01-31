# Minimal Data Endpoints Implementation

## Overview
Minimal data endpoints for financial terminal UI panels. These endpoints provide asset details and macroeconomic series data without requiring authentication.

## Files Created/Modified

### New Files
1. **`services/data_provider_service.py`** - DataProviderService class with:
   - Symbol resolver (AST\d+ -> ticker mapping)
   - yfinance integration for price data and sparklines
   - Polygon.io integration (optional, requires POLYGON_API_KEY)
   - FRED API integration (requires FRED_API_KEY)
   - Deterministic risk data generation
   - TTL caching (10s for asset details, 5min for FRED, 3s for errors)
   - Rate limiting guard (10 requests/second per key)

2. **`api/data.py`** - FastAPI router with two endpoints:
   - `GET /api/asset/detail?symbol=...`
   - `GET /api/macro/series?fred_id=...&limit=200`

### Modified Files
1. **`main.py`** - Added data router import and registration (line 231)
2. **`api/__init__.py`** - Added data module to exports
3. **`requirements.txt`** - Added `requests>=2.31.0` for HTTP API calls

## Endpoints

### 1. GET /api/asset/detail

**Query Parameters:**
- `symbol` (required): Asset symbol (e.g., "AAPL", "AST000001")

**Response:**
```json
{
  "symbol": "AAPL",
  "ticker": "AAPL",
  "name": "Apple Inc.",
  "sector": "Technology",
  "last": 175.43,
  "change_pct": 1.23,
  "sparkline": [175.10, 175.20, 175.35, 175.43],
  "currency": "USD",
  "provider": "yfinance",
  "risk": {
    "risk": 0.45,
    "shock": 0.32,
    "trend": 2,
    "vital": 0.67,
    "macro": 0.51
  },
  "ts": 1704067200000
}
```

**Symbol Resolution:**
- Symbols matching `AST\d+` pattern are mapped deterministically to ~50 liquid tickers via modulo
- Other symbols are treated as tickers directly (uppercased)

**Provider Chain:**
1. Polygon.io (if POLYGON_API_KEY is set) - for last price and change_pct
2. yfinance (fallback/primary) - for sparkline, name, sector, currency
3. Mock data (if all providers fail)

**Caching:** 10 seconds for successful responses, 3 seconds for errors

### 2. GET /api/macro/series

**Query Parameters:**
- `fred_id` (required): FRED series ID (e.g., "GDP", "UNRATE", "CPIAUCSL")
- `limit` (optional, default=200): Maximum number of observations (1-500, capped at 500)

**Response:**
```json
{
  "fred_id": "GDP",
  "series": [
    {"t": "2023-10-01", "v": 27754.1},
    {"t": "2023-07-01", "v": 27575.2},
    {"t": "2023-04-01", "v": 27389.8}
  ],
  "provider": "fred",
  "ts": 1704067200000
}
```

**Caching:** 5 minutes for successful responses, 3 seconds for errors

## Environment Variables

The following environment variables are used (already set in OS environment, do not print):

- `POLYGON_API_KEY` - Optional, for Polygon.io market data
- `FRED_API_KEY` - Required for FRED macro series

yfinance requires no API key.

## How to Run Locally

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-analytics.txt  # For yfinance
   ```

2. **Environment variables** (already set in OS, do not modify):
   - `POLYGON_API_KEY` - Optional
   - `FRED_API_KEY` - Required for FRED endpoints

3. **Start the backend:**
   ```bash
   python main.py
   # Or
   uvicorn main:app --reload
   ```

4. **Backend will be available at:**
   - `http://localhost:8000`
   - API docs: `http://localhost:8000/api/docs` (if DEBUG=True)

## Testing with curl

### Test 1: Asset Detail for AST000001

```bash
curl "http://localhost:8000/api/asset/detail?symbol=AST000001"
```

**Expected:** Symbol `AST000001` will be mapped deterministically to a liquid ticker (e.g., `AAPL`), and response includes price, sparkline, and risk data.

### Test 2: Asset Detail for AAPL

```bash
curl "http://localhost:8000/api/asset/detail?symbol=AAPL"
```

**Expected:** Direct ticker lookup for Apple Inc. with real market data (if yfinance/Polygon available) or mock data.

### Test 3: FRED Series for CPIAUCSL

```bash
curl "http://localhost:8000/api/macro/series?fred_id=CPIAUCSL&limit=200"
```

**Expected:** Consumer Price Index series data with ISO8601 timestamps and values.

### Test 4: FRED Series for UNRATE

```bash
curl "http://localhost:8000/api/macro/series?fred_id=UNRATE&limit=200"
```

**Expected:** Unemployment rate series data with ISO8601 timestamps and values.

## Safety Features

1. **No API keys in responses** - Keys are never logged or returned
2. **Input validation** - Symbols and FRED IDs validated with allowlist regex:
   - symbol: `^[A-Za-z0-9\.\-\_]{1,20}$`
   - fred_id: `^[A-Za-z0-9\.\-\_]{1,50}$`
3. **Error handling** - Graceful fallbacks to mock data on provider failures
4. **Caching** - Reduces API calls and prevents rate limit issues
5. **Rate limiting** - 10 requests/second per key guard to prevent abuse
6. **Timeout protection** - All external API calls have explicit timeouts:
   - Polygon: 3s connect, 5s read
   - FRED: 5s connect, 10s read
   - yfinance: 5-10s per operation
7. **Server-side logging only** - Errors logged server-side, not exposed to client

## Implementation Details

### DataProviderService Class

- `resolve_ticker(symbol)` - Maps AST\d+ patterns to liquid tickers
- `get_asset_detail(symbol)` - Fetches asset data with provider fallback
- `get_macro_series(fred_id, limit)` - Fetches FRED series (limit capped at 500)
- `_polygon_snapshot(ticker)` - Internal Polygon API adapter
- `_yfinance_quote_and_sparkline(ticker)` - Internal yfinance adapter
- `_fred_series(fred_id, limit)` - Internal FRED API adapter
- `_mock_risk(ticker)` - Deterministic risk data generator

### Rate Limiting

Per-key rate limiting (10 requests/second) prevents abuse. When limit exceeded:
- Serves cached data if available (even if expired)
- Returns mock/empty data if no cache available

### Caching Strategy

- **Asset details:** 10s TTL for successful responses, 3s for errors
- **FRED series:** 5min TTL for successful responses, 3s for errors
- Uses `services/cache_service.py` (Redis if available, in-memory fallback)

## Notes

- The `.env` file is already in `.gitignore` (line 37)
- yfinance is in `requirements-analytics.txt` (optional dependency)
- Endpoints are public (no authentication required)
- Risk data is deterministic and stable per ticker (hash-based)
- Sparkline data is downsampled to max 120 points
- FRED limit is capped at 500 to prevent abuse
