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

export function usePointPicking(
  pointsData: PointData[],
  camera: { panX: number; panY: number; zoom: number },
  pointSize: number
) {
  const [hoveredPoint, setHoveredPoint] = useState<PointData | null>(null)
  const [selectedPoint, setSelectedPoint] = useState<PointData | null>(null)

  const screenToWorld = useCallback((screenX: number, screenY: number, canvasWidth: number, canvasHeight: number) => {
    const ndcX = (screenX / canvasWidth) * 2.0 - 1.0
    const ndcY = 1.0 - (screenY / canvasHeight) * 2.0
    
    const worldX = (ndcX / camera.zoom) - camera.panX
    const worldY = (ndcY / camera.zoom) - camera.panY
    
    return { worldX, worldY }
  }, [camera])

  const findNearestPoint = useCallback((worldX: number, worldY: number, threshold: number): PointData | null => {
    if (pointsData.length === 0) return null
    
    let nearest: PointData | null = null
    let minDist = threshold
    
    for (const point of pointsData) {
      const px = point.x01 * 2.0 - 1.0
      const py = point.y01 * 2.0 - 1.0
      
      const dx = px - worldX
      const dy = py - worldY
      const dist = Math.sqrt(dx * dx + dy * dy)
      
      if (dist < minDist) {
        minDist = dist
        nearest = point
      }
    }
    
    return nearest
  }, [pointsData])

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = e.currentTarget
    const rect = canvas.getBoundingClientRect()
    const canvasX = e.clientX - rect.left
    const canvasY = e.clientY - rect.top
    
    const { worldX, worldY } = screenToWorld(canvasX, canvasY, rect.width, rect.height)
    
    const threshold = (pointSize / 100.0) / camera.zoom
    const nearest = findNearestPoint(worldX, worldY, threshold)
    
    setHoveredPoint(nearest)
  }, [screenToWorld, findNearestPoint, pointSize, camera.zoom])

  const handleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (e.button === 0 && hoveredPoint) {
      setSelectedPoint(hoveredPoint)
    }
  }, [hoveredPoint])

  const clearSelection = useCallback(() => {
    setSelectedPoint(null)
  }, [])

  return {
    hoveredPoint,
    selectedPoint,
    handleMouseMove,
    handleClick,
    clearSelection
  }
}
