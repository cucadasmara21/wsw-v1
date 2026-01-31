/// <reference lib="webworker" />
import { validateVertex28Buffer } from '../lib/vertex28Validation'

type WorkerRequest = {
  type: 'fetch'
  requestId: number
  url: string
  limit: number
}

type WorkerResponse = {
  type: 'points'
  requestId: number
  buf: ArrayBuffer
  byteLength: number
  stride: number
  ts: number
} | {
  type: 'error'
  requestId: number
  error: string
}

const ctx: DedicatedWorkerGlobalScope = self as unknown as DedicatedWorkerGlobalScope

const inflight = new Map<number, AbortController>()

async function fetchPointsBin(url: string, requestId: number): Promise<ArrayBuffer> {
  const ac = new AbortController()
  inflight.set(requestId, ac)
  
  try {
    const response = await fetch(url, {
      signal: ac.signal,
      headers: {
        'Accept': 'application/octet-stream'
      }
    })
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    
    const buf = await response.arrayBuffer()
    inflight.delete(requestId)
    return buf
  } catch (err) {
    inflight.delete(requestId)
    throw err
  }
}

ctx.onmessage = async (ev: MessageEvent<WorkerRequest>) => {
  const msg = ev.data
  
  if (msg.type !== 'fetch') {
    return
  }
  
  for (const [id, ac] of inflight.entries()) {
    if (id < msg.requestId) {
      ac.abort()
      inflight.delete(id)
    }
  }
  
  try {
    const buf = await fetchPointsBin(msg.url, msg.requestId)

    try {
      validateVertex28Buffer(buf)
    } catch (err) {
      const e = err instanceof Error ? err : new Error(String(err))
      ctx.postMessage({ type: 'error', requestId: msg.requestId, error: e.message })
      throw err
    }

    const ts = Date.now()
    const resp: WorkerResponse = {
      type: 'points',
      requestId: msg.requestId,
      buf,
      byteLength: buf.byteLength,
      stride: 28,
      ts
    }

    ctx.postMessage(resp, [buf])

  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      return
    }
    const resp: WorkerResponse = {
      type: 'error',
      requestId: msg.requestId,
      error: err instanceof Error ? err.message : String(err)
    }
    ctx.postMessage(resp)
  }
}
