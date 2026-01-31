# Polling Flood Fix - TitanCanvas.tsx

## Problem
Frontend was flooding `/api/universe/points.bin` with requests every ~5-8ms instead of respecting the 2000ms minimum interval.

## Root Cause
- Polling logic was inside a large useEffect with many dependencies
- `pollOnce` callback dependencies were causing re-creation and re-scheduling
- Multiple potential scheduling points

## Solution
Implemented strict completion-chained polling with:
- Single `pollOnce` useCallback outside the main useEffect
- Separate useEffect that only depends on `pollOnce`
- Single-flight guard (`inFlightRef`)
- AbortController for cancellation
- Minimum 2000ms interval enforced
- Schedule next poll ONLY in finally block

## Changes Made

### 1. Refs (already present, verified)
```typescript
const inFlightRef = useRef(false)
const pollTimerRef = useRef<number | null>(null)
const abortRef = useRef<AbortController | null>(null)
const unmountedRef = useRef(false)
```

### 2. Helper (already present, verified)
```typescript
const clearPollTimer = useCallback(() => {
  if (pollTimerRef.current != null) {
    window.clearTimeout(pollTimerRef.current)
    pollTimerRef.current = null
  }
}, [])
```

### 3. pollOnce useCallback (moved outside main useEffect)
```typescript
const pollOnce = useCallback(async () => {
  if (unmountedRef.current) return
  if (inFlightRef.current) return

  const effectivePollMs = Math.max(2000, pollMs > 0 ? pollMs : 2000)

  inFlightRef.current = true
  clearPollTimer()

  abortRef.current?.abort()
  const ac = new AbortController()
  abortRef.current = ac

  try {
    await fetchPointsBinary({ signal: ac.signal })
    // Symbols: only fetch if missing (lazy load, not on every poll)
    if (!symbolsLoadedRef.current) {
      await fetchSymbolsIfNeeded({ signal: ac.signal })
    }
  } catch (err: any) {
    if (err?.name !== 'AbortError') {
      console.error('pollOnce error', err)
    }
  } finally {
    inFlightRef.current = false
    if (unmountedRef.current) return
    pollTimerRef.current = window.setTimeout(() => {
      void pollOnce()
    }, effectivePollMs)
  }
}, [pollMs, fetchPointsBinary, fetchSymbolsIfNeeded, clearPollTimer])
```

### 4. Separate useEffect for Polling
```typescript
useEffect(() => {
  unmountedRef.current = false
  symbolsLoadedRef.current = false // Reset symbols on new effect instance
  void pollOnce() // Start immediately once
  return () => {
    unmountedRef.current = true
    clearPollTimer()
    abortRef.current?.abort()
    abortRef.current = null
    inFlightRef.current = false
  }
}, [pollOnce])
```

### 5. Removed from Main useEffect
- Removed `pollOnce` definition from inside the main useEffect
- Removed direct `pollOnce()` call from main useEffect
- Cleaned up dependencies to only include `[streamUrlBin, onAssetClick]`

## Verification Checklist

✅ **No setInterval**: Confirmed no `setInterval` calls exist  
✅ **Single pollOnce**: Only one `pollOnce` definition  
✅ **Completion-chained**: Next poll scheduled ONLY in finally block  
✅ **Single-flight**: `inFlightRef` guard prevents overlaps  
✅ **AbortController**: Aborts on unmount and before new poll  
✅ **Minimum interval**: `effectivePollMs = Math.max(2000, pollMs > 0 ? pollMs : 2000)`  
✅ **Symbols lazy load**: `fetchSymbolsIfNeeded` only called if `!symbolsLoadedRef.current`  
✅ **Cleanup**: Timer cleared, abort called, flags reset on unmount  

## What Was Removed

1. **Old polling logic** inside main useEffect that was causing re-scheduling
2. **Direct `pollOnce()` call** from main useEffect cleanup
3. **Multiple scheduling points** - now only one (in finally block)

## What Was Added

1. **pollOnce useCallback** moved outside main useEffect (proper memoization)
2. **Separate useEffect** for polling with minimal dependencies `[pollOnce]`
3. **Strict guards**: unmountedRef check, inFlightRef check, effectivePollMs enforcement

## PowerShell Commands (Run Manually)

### 1. Start Frontend Dev Server
```powershell
cd C:\Users\alber\Documents\wsw-v1\frontend
npm run dev
```

### 2. Verification Steps (Chrome DevTools)
1. Open: `http://127.0.0.1:5173/universe`
2. Open DevTools (F12)
3. Go to Network tab
4. Filter: `points.bin`
5. Wait 10 seconds
6. **EXPECTATION**: At most ~5 requests in 10s (one every 2s)
7. **VERIFY**: No overlapping "pending" requests (only one pending at a time)

### 3. If Still Flooding
- Check console for errors
- Verify `effectivePollMs` is being computed correctly (should be ≥2000)
- Check if `pollOnce` dependencies are changing frequently (causing re-creation)

## Expected Behavior

- **First request**: Immediate (on mount)
- **Subsequent requests**: Every 2000ms minimum
- **No overlaps**: Only one `points.bin` request pending at a time
- **Symbols**: Fetched only once (lazy load), not on every poll
- **Unmount**: All timers cleared, requests aborted
