import React, { useEffect, useState } from 'react'
import StatusCard from '../components/StatusCard'
import TableList from '../components/TableList'
import { fetchRootJson, fetchApiRaw, fetchApiJson } from '../lib/api'

export default function DashboardPage(){
  // --- Types for Risk Summary SQL response (used only in this component)
  type RiskVectorAvg = {
    price_risk: number
    fundamental_risk: number
    liquidity_risk: number
    counterparty_risk: number
    regime_risk: number
  }

  type TopRiskItem = {
    asset_id: string
    asset_name: string
    group_name: string
    subgroup_name: string
    category_name: string
    cri: number
    risk_vector: RiskVectorAvg
  }

  type RiskSummarySqlResponse = {
    as_of: string | null
    universe: number
    cri_avg: number
    vector_avg: RiskVectorAvg
    top_risks: Record<string, TopRiskItem[]>
  }

  const [health, setHealth] = useState<any|null>(null)
  const [version, setVersion] = useState<any|null>(null)
  const [riskOverview, setRiskOverview] = useState<any|null>(null)
  const [riskLoading, setRiskLoading] = useState(false)
  const [riskError, setRiskError] = useState<string|null>(null)
  const [scenario, setScenario] = useState('market_crash')
  const [running, setRunning] = useState(false)
  const [runResult, setRunResult] = useState<any|null>(null)
  const [runError, setRunError] = useState<string|null>(null)

  // State for SQL-only Risk Summary
  const [riskSummary, setRiskSummary] = useState<RiskSummarySqlResponse | null>(null)
  const [riskSummaryLoading, setRiskSummaryLoading] = useState(false)
  const [riskSummaryError, setRiskSummaryError] = useState<string|null>(null)

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
        const res = await fetchApiRaw('/risk/overview')
        if (res.status === 404){
          setRiskOverview(null)
          setRiskError('Not available')
          return
        }
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
        const data = await res.json()
        setRiskOverview(data)
      }catch(e:any){
        setRiskError(e.message)
      }finally{ setRiskLoading(false) }
    })()
  },[])

  // Fetch the SQL-only risk summary using the same API helper pattern
  const fetchRiskSummary = async () => {
    setRiskSummaryLoading(true)
    setRiskSummaryError(null)
    try{
      const data = await fetchApiJson<RiskSummarySqlResponse>('/risk/summary_sql')
      setRiskSummary(data)
    }catch(e:any){
      setRiskSummaryError(e?.message ?? 'Failed to load')
      setRiskSummary(null)
    }finally{ setRiskSummaryLoading(false) }
  }

  useEffect(()=>{ fetchRiskSummary() }, [])

  const averageCRI = (overview:any|null) => {
    if (!overview) return 0
    return Math.round((overview.cri_avg||0)*100)/100
  }

  const topN = (overview:any|null, n:number) => {
    if (!overview || !overview.top_assets) return []
    return overview.top_assets.slice(0,n)
  }

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
        {!riskLoading && !riskError && !riskOverview && <div>No risk data</div>}
        {riskOverview && (
        <div>
          <div style={{display:'flex',gap:12,marginBottom:12}}>
            <StatusCard title="Average CRI"><div style={{fontSize:20,fontWeight:600}}>{averageCRI(riskOverview)}</div></StatusCard>
            <StatusCard title="Price Risk"><div>{(riskOverview.vector_avg.price_risk||0).toFixed(2)}</div></StatusCard>
            <StatusCard title="Fundamental"><div>{(riskOverview.vector_avg.fundamental_risk||0).toFixed(2)}</div></StatusCard>
            <StatusCard title="Liquidity"><div>{(riskOverview.vector_avg.liquidity_risk||0).toFixed(2)}</div></StatusCard>
            <StatusCard title="Counterparty"><div>{(riskOverview.vector_avg.counterparty_risk||0).toFixed(2)}</div></StatusCard>
            <StatusCard title="Regime"><div>{(riskOverview.vector_avg.regime_risk||0).toFixed(2)}</div></StatusCard>
          </div>

          <TableList columns={["asset_name","group_name","subgroup_name","category_name","cri"]} rows={riskOverview.top_assets} renderCell={(row,col)=> (row as any)[col] ?? '-'} />
        </div>
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

      <StatusCard title="Risk Summary (SQL) — Top 5 by Type">
        <div style={{display:'flex', justifyContent:'space-between', alignItems:'center'}}>
          <div>
            <small>Endpoint: <code>/api/risk/summary_sql</code></small>
          </div>
          <div>
            <button onClick={()=>fetchRiskSummary()} disabled={riskSummaryLoading} style={{marginRight:8}}>Refresh</button>
            {riskSummaryError && <button onClick={()=>fetchRiskSummary()}>Retry</button>}
          </div>
        </div>

        {riskSummaryLoading && <div>Loading...</div>}
        {riskSummaryError && <div className="error">{riskSummaryError}</div>}

        {(!riskSummary && !riskSummaryLoading && !riskSummaryError) && <div>No summary available</div>}

        {riskSummary && (
          <div>
            <div style={{display:'flex',gap:12,marginTop:8}}>
              <div><strong>As of:</strong> {riskSummary.as_of}</div>
              <div><strong>Universe:</strong> {riskSummary.universe}</div>
              <div><strong>Avg CRI:</strong> {Math.round(riskSummary.cri_avg*100)/100}</div>
            </div>

            <div style={{display:'flex',gap:12,marginTop:8,marginBottom:8}}>
              <StatusCard title="Price Risk"><div>{riskSummary.vector_avg.price_risk.toFixed(2)}</div></StatusCard>
              <StatusCard title="Fundamental"><div>{riskSummary.vector_avg.fundamental_risk.toFixed(2)}</div></StatusCard>
              <StatusCard title="Liquidity"><div>{riskSummary.vector_avg.liquidity_risk.toFixed(2)}</div></StatusCard>
              <StatusCard title="Counterparty"><div>{riskSummary.vector_avg.counterparty_risk.toFixed(2)}</div></StatusCard>
              <StatusCard title="Regime"><div>{riskSummary.vector_avg.regime_risk.toFixed(2)}</div></StatusCard>
            </div>

            {/* Render a table per risk type */}
            {Object.keys(riskSummary.top_risks).map((rk)=>{
              const rows = (riskSummary.top_risks as any)[rk] as TopRiskItem[]
              const mapped = rows.map(r=> ({...r, score: (r.risk_vector as any)[rk] ?? 0}))
              return (
                <div key={rk} style={{marginBottom:12}}>
                  <h4 style={{textTransform:'capitalize'}}>{rk.replace('_',' ')} — Top 5</h4>
                  <TableList columns={["asset_name","group_name","subgroup_name","category_name","score"]} rows={mapped} renderCell={(row,col)=> (row as any)[col] ?? '-'} />
                </div>
              )
            })}

          </div>
        )}
      </StatusCard>

    </div>
  )
}
