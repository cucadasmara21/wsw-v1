# TitanCanvas.tsx Restoration Note

## Issue
The file `frontend/src/components/TitanCanvas.tsx` was accidentally overwritten and now only contains 78 lines of bloom shader code instead of the full ~1200+ line component.

## Required Exports (from UniversePage.tsx)
```typescript
import { TitanCanvas, type TitanCanvasRef } from '../components/TitanCanvas'
```

## What Needs to Be Restored

The file should contain:
1. **Exports**:
   - `export interface TitanCanvasRef { refresh: () => void; focusPoint: (point: PointData) => void }`
   - `export interface TitanCanvasProps { ... }`
   - `export const TitanCanvas = forwardRef<TitanCanvasRef, TitanCanvasProps>(...)`

2. **Component Structure**:
   - All imports (React, WebGL, hooks, etc.)
   - All shader code (TITAN_VERTEX_SHADER, TITAN_FRAGMENT_SHADER, SINGULARITY_FRAGMENT_SHADER)
   - Picking worker code
   - All refs (pollEpochRef, pollTimerRef, inFlightRef, etc.)
   - Polling useEffect (lines 1002-1081 with canonical structure)
   - WebGL setup and render loop
   - All helper functions (fetchPoints, fetchSymbols, processPointsData, etc.)

3. **Key Features**:
   - Polling with canonical structure (already fixed)
   - WebGL2 rendering
   - Grid-based picking worker
   - Click-to-detail integration (onAssetClick callback)

## Temporary Fix
A minimal export stub has been created to allow the app to boot, but the full implementation needs to be restored from:
- Git history (if committed)
- Backup
- Previous working version

## Next Steps
1. Restore full TitanCanvas.tsx from backup/version control
2. Verify all exports match UniversePage.tsx expectations
3. Test that polling, rendering, and picking still work
