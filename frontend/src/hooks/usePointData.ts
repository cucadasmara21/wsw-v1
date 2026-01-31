import { useRef, useState, useCallback } from 'react'

export interface PointData {
  index: number
  x01: number
  y01: number
  shock: number
  risk: number
  trend: number
  vital: number
  macro: number
  symbol: string
  assetId: number
}

export function usePointData() {
  const [pointsData, setPointsData] = useState<PointData[]>([])
  const symbolsRef = useRef<Map<number, string>>(new Map())

  const decodePoints = useCallback(async (buf: ArrayBuffer, symbols: Map<number, string>, bounds: { minX: number; maxX: number; minY: number; maxY: number }): Promise<PointData[]> => {
    const view = new DataView(buf)
    // Route A: Vertex28 only.
    const count = Math.floor(buf.byteLength / 28)
    const denomX = Math.max(1, bounds.maxX - bounds.minX)
    const denomY = Math.max(1, bounds.maxY - bounds.minY)

    const decoded: PointData[] = []

    for (let i = 0; i < count; i++) {
      const off = i * 28
      // <IIfffff
      const meta32 = view.getUint32(off + 4, true)
      const x = view.getFloat32(off + 8, true)
      const y = view.getFloat32(off + 12, true)
      // z is at +16 but unused for this hook

      const x01 = Math.max(0, Math.min(1, (x - bounds.minX) / denomX))
      const y01 = Math.max(0, Math.min(1, (y - bounds.minY) / denomY))

      const shock = (meta32 & 0xFF) / 255.0
      const risk = ((meta32 >> 8) & 0xFF) / 255.0
      const trend = (meta32 >> 16) & 0x03
      const vital = ((meta32 >> 18) & 0x3F) / 63.0
      const macro = ((meta32 >> 24) & 0xFF) / 255.0

      const assetId = i + 1
      const symbol = symbols.get(assetId) || symbols.get(i + 1) || `ASSET-${assetId}`

      decoded.push({
        index: i,
        x01,
        y01,
        shock,
        risk,
        trend,
        vital,
        macro,
        symbol,
        assetId
      })
    }

    setPointsData(decoded)
    return decoded
  }, [])

  const loadSymbols = useCallback(async (limit: number = 10000): Promise<Map<number, string>> => {
    // Route A: legacy points.symbols removed.
    // Symbol mapping is handled via /api/assets list / picking metadata.
    const map = new Map<number, string>()
    symbolsRef.current = map
    return map
  }, [])

  return {
    pointsData,
    decodePoints,
    loadSymbols
  }
}
