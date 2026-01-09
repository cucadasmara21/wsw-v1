import React, { useEffect, useState } from 'react'
import StatusCard from '../components/StatusCard'
import TableList from '../components/TableList'
import { fetchRootJson, fetchApiRaw, fetchApiJson } from '../lib/api'

export default function DashboardPage(){
  const [health, setHealth] = useState<any|null>(null)
  const [version, setVersion] = useState<any|null>(null)
  const [risk, setRisk] = useState<any[]|null>(null)
  const [riskLoading, setRiskLoading] = useState(false)
  const [riskError, setRiskError] = useState<string|null>(null)
  const [scenario, setScenario] = useState('market_crash')
  const [running, setRunning] = useState(false)
  const [runResult, setRunResult] = useState<any|null>(null)
  const [runError, setRunError] = useState<string|null>(null)

  useEffect(()=>{
    ;(async ()=>{
      try{ const h = await fetchRootJson('/health'); setHealth(h) }catch(_){}
      try{ const v = await fetchRootJson('/version'); setVersion(v) }catch(_){}
    })()
  },[])

  useEffect(()=>{
    ;(async ()=>{
      setRiskLoading(true)
      setRiskError(null)
      try{
        // use raw fetch to detect 404 (Not available)
        const res = await fetchApiRaw('/risk/overview')
        if (res.status === 404){
          setRisk(null)
          setRiskError('Not available')
          return
        }
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
        const data = await res.json()
        setRisk(data)
      }catch(e:any){
        setRiskError(e.message)
      }finally{ setRiskLoading(false) }
    })()
  },[])

  const runScenario = async () => {
    setRunning(true); setRunError(null); setRunResult(null)
    try{
      const url = `/scenarios/run?scenario_name=${encodeURIComponent(scenario)}`
      // Try POST first
      let res = await fetchApiRaw(url, { method: 'POST' })
      if (res.status === 404 || res.status === 405) {
        // fallback to GET if POST not supported
        res = await fetchApiRaw(url, { method: 'GET' })
      }
      if (!res.ok){
        const text = await res.text()
        throw new Error(`${res.status} ${res.statusText}: ${text.slice(0,200)}`)
      }
      const data = await res.json()
      setRunResult(data)
    }catch(e:any){ setRunError(e.message) }finally{ setRunning(false) }
  }

  return (
    <div>
      <h1>Dashboard</h1>

      <StatusCard title="System Status">
        <div style={{display:'flex',gap:12}}>
          <div style={{flex:1}}>
            <h4>Health</h4>
            <pre style={{maxHeight:200,overflow:'auto'}}>{health ? JSON.stringify(health,null,2) : 'Unavailable'}</pre>
          </div>
          <div style={{flex:1}}>
            <h4>Version</h4>
            <pre style={{maxHeight:200,overflow:'auto'}}>{version ? JSON.stringify(version,null,2) : 'Unavailable'}</pre>
          </div>
        </div>
      </StatusCard>

      <StatusCard title="Risk Overview">
        {riskLoading && <div>Loading risk overview...</div>}
        {riskError && <div>{riskError}</div>}
        {risk && risk.length === 0 && <div>No risk items</div>}
        {risk && risk.length > 0 && (
          <TableList columns={Object.keys(risk[0])} rows={risk} renderCell={(row,col)=> (row as any)[col] ?? '-'} />
        )}
      </StatusCard>

      <StatusCard title="Scenario Runner">
        <div>
          <label>Scenario name: <input value={scenario} onChange={e=>setScenario(e.target.value)} /></label>
          <button onClick={runScenario} disabled={running} style={{marginLeft:8}}>{running ? 'Running...' : 'Run'}</button>
        </div>
        {runError && <div className="error">{runError}</div>}
        {runResult && <pre style={{marginTop:8}}>{JSON.stringify(runResult,null,2)}</pre>}
      </StatusCard>

    </div>
  )
}
