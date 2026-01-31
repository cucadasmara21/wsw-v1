import { useRef, useState, useCallback } from 'react'

export interface CameraState {
  panX: number
  panY: number
  zoom: number
}

export function useCamera(initialZoom: number = 1.0) {
  const [camera, setCamera] = useState<CameraState>({
    panX: 0.0,
    panY: 0.0,
    zoom: initialZoom
  })

  const isDraggingRef = useRef(false)
  const lastMouseRef = useRef({ x: 0, y: 0 })

  const reset = useCallback(() => {
    setCamera({ panX: 0.0, panY: 0.0, zoom: initialZoom })
  }, [initialZoom])

  const pan = useCallback((dx: number, dy: number) => {
    setCamera(prev => ({
      ...prev,
      panX: prev.panX + dx,
      panY: prev.panY + dy
    }))
  }, [])

  const zoomAt = useCallback((x: number, y: number, delta: number) => {
    setCamera(prev => {
      const zoomFactor = delta > 0 ? 1.1 : 0.9
      const newZoom = Math.max(0.1, Math.min(10.0, prev.zoom * zoomFactor))
      
      const worldX = (x / window.innerWidth) * 2.0 - 1.0
      const worldY = 1.0 - (y / window.innerHeight) * 2.0
      
      const zoomRatio = newZoom / prev.zoom
      const newPanX = worldX - (worldX - prev.panX) * zoomRatio
      const newPanY = worldY - (worldY - prev.panY) * zoomRatio
      
      return {
        panX: newPanX,
        panY: newPanY,
        zoom: newZoom
      }
    })
  }, [])

  const focus = useCallback((worldX: number, worldY: number, targetZoom: number = 2.0) => {
    const targetPanX = -worldX
    const targetPanY = -worldY
    const targetZoomClamped = Math.max(0.1, Math.min(10.0, targetZoom))
    
    setCamera(prev => {
      const steps = 30
      let currentPanX = prev.panX
      let currentPanY = prev.panY
      let currentZoom = prev.zoom
      
      const animate = (step: number) => {
        if (step >= steps) {
          setCamera({
            panX: targetPanX,
            panY: targetPanY,
            zoom: targetZoomClamped
          })
          return
        }
        
        const t = step / steps
        const ease = t * (2 - t)
        
        currentPanX = prev.panX + (targetPanX - prev.panX) * ease
        currentPanY = prev.panY + (targetPanY - prev.panY) * ease
        currentZoom = prev.zoom + (targetZoomClamped - prev.zoom) * ease
        
        setCamera({
          panX: currentPanX,
          panY: currentPanY,
          zoom: currentZoom
        })
        
        requestAnimationFrame(() => animate(step + 1))
      }
      
      animate(0)
      return prev
    })
  }, [])

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button === 0) {
      isDraggingRef.current = true
      lastMouseRef.current = { x: e.clientX, y: e.clientY }
      e.preventDefault()
    }
  }, [])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (isDraggingRef.current) {
      const dx = (e.clientX - lastMouseRef.current.x) / (window.innerWidth / 2.0)
      const dy = -(e.clientY - lastMouseRef.current.y) / (window.innerHeight / 2.0)
      pan(dx * camera.zoom, dy * camera.zoom)
      lastMouseRef.current = { x: e.clientX, y: e.clientY }
    }
  }, [camera.zoom, pan])

  const handleMouseUp = useCallback(() => {
    isDraggingRef.current = false
  }, [])

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    zoomAt(e.clientX, e.clientY, e.deltaY)
  }, [zoomAt])

  return {
    camera,
    reset,
    pan,
    zoomAt,
    focus,
    handleMouseDown,
    handleMouseMove,
    handleMouseUp,
    handleWheel
  }
}
