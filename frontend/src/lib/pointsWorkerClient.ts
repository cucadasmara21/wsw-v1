interface PointsData {
  buf: ArrayBuffer
  byteLength: number
  stride: number
  ts: number
}

type OnDataCallback = (data: PointsData) => void
type OnErrorCallback = (error: string) => void

class PointsWorkerClient {
  private worker: Worker | null = null
  private requestId = 0
  private currentRequestId = 0
  private onDataCallback: OnDataCallback | null = null
  private onErrorCallback: OnErrorCallback | null = null

  constructor() {
    this.initWorker()
  }

  private initWorker() {
    if (this.worker) {
      this.worker.terminate()
    }

    this.worker = new Worker(
      new URL('../workers/pointsWorker.ts', import.meta.url),
      { type: 'module' }
    )

    this.worker.onmessage = (ev: MessageEvent) => {
      const msg = ev.data

      if (msg.type === 'points') {
        if (msg.requestId !== this.currentRequestId) {
          return
        }

        if (this.onDataCallback) {
          this.onDataCallback({
            buf: msg.buf,
            byteLength: msg.byteLength,
            stride: msg.stride,
            ts: msg.ts
          })
        }
      } else if (msg.type === 'error') {
        if (msg.requestId !== this.currentRequestId) {
          return
        }

        if (this.onErrorCallback) {
          this.onErrorCallback(msg.error)
        }
      }
    }

    this.worker.onerror = (err) => {
      if (this.onErrorCallback) {
        this.onErrorCallback(`Worker error: ${err.message}`)
      }
    }
  }

  subscribe(onData: OnDataCallback, onError?: OnErrorCallback) {
    this.onDataCallback = onData
    this.onErrorCallback = onError || null
  }

  async fetch(limit: number = 10000): Promise<void> {
    this.requestId++
    this.currentRequestId = this.requestId

    if (!this.worker) {
      this.initWorker()
    }

    // Route A: legacy points.bin removed. Use V8 snapshot.
    const url = `/api/universe/v8/snapshot?format=vertex28&compression=none&limit=${limit}`
    
    this.worker.postMessage({
      type: 'fetch',
      requestId: this.currentRequestId,
      url: url,
      limit: limit
    })
  }

  unsubscribe() {
    this.onDataCallback = null
    this.onErrorCallback = null
  }

  destroy() {
    if (this.worker) {
      this.worker.terminate()
      this.worker = null
    }
    this.onDataCallback = null
    this.onErrorCallback = null
  }
}

let clientInstance: PointsWorkerClient | null = null

export function getPointsWorkerClient(): PointsWorkerClient {
  if (!clientInstance) {
    clientInstance = new PointsWorkerClient()
  }
  return clientInstance
}

export type { PointsData }
