export const API_BASE = import.meta.env.VITE_API_URL ?? '/api'

export async function fetchJson<T = any>(path: string) {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${text.slice(0, 200)}`)
  }
  return res.json() as Promise<T>
}
