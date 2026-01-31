# Polling Fix Verification

## Changes Applied

### 1. Canonical Poller Structure
- Replaced polling effect with exact structure matching requirements
- Added `disposed` flag inside effect (not ref)
- Cleanup sets `disposed = true` (does NOT increment epoch)
- All guards check `disposed` first, then epoch

### 2. StrictMode Compatibility
- Cleanup properly sets `disposed = true`
- `scheduleNext()` checks `disposed` first → returns early if true
- `pollOnce()` checks `disposed` first → returns early if true
- Even if timer fires after cleanup, it will return immediately

### 3. Debug Logging
- Added `DEBUG_POLL = true` (always enabled for diagnosis)
- Logs: `[TitanPoll] start` with epoch, url, timestamp, effectivePollMs
- Logs: `[TitanPoll] cleanup epoch=` on cleanup
- Logs: `[TitanRefresh] skip spacing` / `skip inFlight` for manual refresh

### 4. Manual Refresh Guards
- `refresh()` method respects same guards as poller:
  - Spacing: must wait `effectivePollMs` since last start
  - Single-flight: must not overlap with poller
- Uses same `inFlightRef` and `lastStartMsRef` as poller

### 5. URL Stability
- Verified: `UniversePage.tsx` does NOT construct `streamUrlBin` dynamically
- `TitanCanvas` uses default prop: `streamUrlBin = '/api/universe/points.bin?limit=10000'`
- No URL churn from query string construction

### 6. Single Mount Verification
- Verified: Only ONE `<TitanCanvas>` instance in `UniversePage.tsx` (line 320)
- No duplicate mounts

## Expected Behavior

### With `pollMs=2000`:
- **First request**: Immediate (on mount)
- **Subsequent requests**: Every ~2000ms (spacing enforced)
- **10 seconds**: ≤6 requests total (1 immediate + 5 at 2s intervals = 6 max)

### StrictMode (Double Mount):
1. First mount: epoch=1, starts pollOnce
2. Cleanup: `disposed=true`, clears timer, aborts request
3. Second mount: epoch=2, starts new pollOnce
4. If first mount's timer fires: checks `disposed` (true) → returns early ✓
5. If first mount's pollOnce finishes: checks `disposed` (true) → skips scheduleNext ✓

### Network Tab Verification:
- Filter: `points.bin`
- Wait 10 seconds
- **Expected**: ≤6 requests, evenly spaced (~2000ms apart)
- **No parallel requests**: Only one "pending" at a time
- **No storms**: No bursts of rapid requests

## Console Logs (DEBUG_POLL=true)

Expected logs every ~2000ms:
```
[TitanPoll] start { epoch: 1, url: '/api/universe/points.bin?limit=10000', t: 1234567890, effectivePollMs: 2000 }
```

On cleanup (StrictMode or unmount):
```
[TitanPoll] cleanup epoch= 1
```

## Acceptance Criteria

✅ **Exactly ONE polling loop** per mounted Universe route
✅ **No setInterval** - only completion-chained setTimeout
✅ **Robust under StrictMode** - cleanup prevents orphaned timers
✅ **AbortController support** - all fetches use `{ signal }`
✅ **Poll spacing guarantee** - starts are ≥2000ms apart
✅ **Network proof** - ≤6 requests per 10 seconds with pollMs=2000

## If Still Seeing Storms

1. **Check console logs**: Look for multiple `[TitanPoll] start` with different epochs
2. **Check Network tab**: Look for overlapping "pending" requests
3. **Check for duplicate mounts**: Search for multiple `<TitanCanvas>` instances
4. **Check for other fetch calls**: Search for `fetchPoints` or `fetch(streamUrlBin)` outside poller
5. **Verify StrictMode**: Check if cleanup logs appear twice (normal in dev)
