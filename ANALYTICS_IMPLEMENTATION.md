# Real-Time Signal Injection (CUSUM/RLS/VPIN) Implementation

## Overview

This implementation adds real-time signal injection into the existing `points.bin` binary format **without changing the binary contract** (`<HHII`, 12 bytes per point).

## Architecture

### Components

1. **Analytics Engine** (`analytics/engine.py`)
   - Orchestrates CUSUM, RLS, and VPIN detectors
   - Maintains numpy arrays for efficient batch updates
   - Thread-safe with RLock

2. **CUSUM Detector** (`analytics/cusum.py`)
   - Detects sudden changes in price returns
   - Outputs `shock8` (0-255) based on cumulative deviation

3. **RLS Detector** (`analytics/rls.py`)
   - Recursive Least Squares for trend detection
   - Outputs `trend2`: 0 (flat), 1 (bull), 2 (bear)

4. **VPIN Calculator** (`analytics/vpin.py`)
   - Volume-synchronized Probability of Informed Trading
   - Outputs `risk8` (0-255) and `vital6` (0-63)

5. **Points Buffer Service** (`services/points_buffer_service.py`)
   - Thread-safe shared buffer for `/api/universe/points.bin`
   - Supports in-place updates of `meta32` fields

6. **Analytics Ticker Service** (`services/analytics_ticker_service.py`)
   - Background task that fetches prices and updates signals
   - Broadcasts diffs via WebSocket

7. **WebSocket Endpoint** (`api/websocket.py`)
   - `/ws/universe` endpoint for real-time updates
   - Sends binary diff frames: `[u32 count][repeated: u32 index, u32 attr, u32 meta]`

## Bit Packing (meta32)

The `meta32` field uses the following bit allocation (matches `ingest_service.py`):

```
bits [0..7]   : shock8  (0-255)   - CUSUM shock intensity
bits [8..15]  : risk8   (0-255)   - VPIN risk score
bits [16..17] : trend2  (0-3)     - RLS trend: 0=flat, 1=bull, 2=bear
bits [18..23] : vital6  (0-63)    - VPIN vitality/liquidity proxy
bits [24..31] : macro8  (0-255)   - Macro signal (global)
```

Packing function:
```python
def pack_meta32(shock8: int, risk8: int, trend2: int, vital6: int, macro8: int) -> int:
    shock8 &= 0xFF
    risk8 &= 0xFF
    trend2 &= 0x03
    vital6 &= 0x3F
    macro8 &= 0xFF
    return shock8 | (risk8 << 8) | (trend2 << 16) | (vital6 << 18) | (macro8 << 24)
```

## WebSocket Protocol

### Connection
- Endpoint: `/ws/universe`
- On connect: sends JSON hello message with `build_tag: "TITAN_V8_ANALYTICS"`

### Binary Diff Frame Format
```
[u32 count]                    # Number of updates
[repeated for each update:]
  [u32 index]                  # Asset index (0-based)
  [u32 attr]                   # Taxonomy32 (currently 0, can be enhanced)
  [u32 meta32]                 # Updated meta32 value
```

### Example Frame (2 updates)
```
[0x02 0x00 0x00 0x00]          # count = 2
[0x00 0x00 0x00 0x00]          # index = 0
[0x00 0x00 0x00 0x00]          # attr = 0
[0x80 0x80 0x00 0x80]          # meta32 = 0x80800080 (shock=128, risk=128, trend=0, vital=32, macro=128)
[0x01 0x00 0x00 0x00]          # index = 1
[0x00 0x00 0x00 0x00]          # attr = 0
[0xFF 0xFF 0x01 0xFF]          # meta32 = 0xFFFF01FF (shock=255, risk=255, trend=1, vital=0, macro=255)
```

## Background Task

The analytics ticker service runs as a background task:

1. **Initialization** (on FastAPI startup):
   - Loads assets from database
   - Builds symbol -> index mapping
   - Initializes analytics engine
   - Initializes shared points buffer

2. **Tick Loop** (default: 1000ms interval):
   - Fetches prices (yfinance if available, else stub)
   - Updates analytics engine (CUSUM/RLS/VPIN)
   - Updates shared buffer in-place
   - Broadcasts diffs via WebSocket

3. **Shutdown** (on FastAPI shutdown):
   - Stops ticker task gracefully

## Performance

- **Efficient**: Uses numpy arrays for batch operations
- **Thread-safe**: RLock guards all shared state
- **Non-blocking**: Background task doesn't block HTTP requests
- **Scalable**: Handles 10k+ assets efficiently

## Testing

### Quick Test Script

```python
# Test analytics engine
from analytics.engine import AnalyticsEngine

engine = AnalyticsEngine(asset_count=100, macro8=128)
engine.initialize_asset(0, 1, 100.0)

# Simulate price updates
prices = {"SYNT-000000": 101.0}
index_map = {"SYNT-000000": 0}

updated = engine.tick(prices, index_map)
print(f"Updated indices: {updated}")

shock, risk, trend, vital, macro = engine.get_signals(0)
print(f"Signals: shock={shock}, risk={risk}, trend={trend}, vital={vital}, macro={macro}")
```

### WebSocket Test

```bash
# Using wscat (npm install -g wscat)
wscat -c ws://127.0.0.1:8000/api/ws/universe

# Expected: JSON hello message, then binary diff frames
```

## Configuration

- **Tick Interval**: Default 1000ms (configurable in `AnalyticsTickerService`)
- **CUSUM Threshold**: Default 0.02 (configurable in `CUSUMDetector`)
- **RLS Forgetting Factor**: Default 0.95 (configurable in `RLSTrendDetector`)
- **VPIN Window**: Default 50 buckets (configurable in `VPINCalculator`)

## Notes

- **Binary Contract Preserved**: No changes to `<HHII` struct or 12-byte stride
- **Backward Compatible**: `/api/universe/points.bin` still works (falls back to DB if buffer not initialized)
- **Graceful Degradation**: Falls back to stub prices if yfinance unavailable
- **Thread-Safe**: All shared state protected by locks
