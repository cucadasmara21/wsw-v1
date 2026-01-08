import React, { useState } from 'react'

export default function ScenarioForm(){
  const [name, setName] = useState('Test scenario')
  const [nodes, setNodes] = useState('')
  const [intensity, setIntensity] = useState(1)
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setResult(null)
    try{
      const payload = { name, nodes: nodes ? nodes.split(',').map(s=>s.trim()) : [], intensity: Number(intensity) }
      const res = await fetch('/api/scenarios/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      const data = await res.json()
      setResult(data)
    }catch(e:any){
      setResult({ error: e.message })
    }finally{ setLoading(false) }
  }

  return (
    <form onSubmit={submit}>
      <div>
        <label>Name: <input value={name} onChange={e=>setName(e.target.value)} /></label>
      </div>
      <div>
        <label>Nodes (comma separated): <input value={nodes} onChange={e=>setNodes(e.target.value)} /></label>
      </div>
      <div>
        <label>Intensity: <input type="number" step="0.1" value={intensity} onChange={e=>setIntensity(Number(e.target.value))} /></label>
      </div>
      <div>
        <button type="submit" disabled={loading}>{loading ? 'Running...' : 'Run'}</button>
      </div>
      {result && (
        <pre style={{ marginTop: 8 }}>{JSON.stringify(result, null, 2)}</pre>
      )}
    </form>
  )
}