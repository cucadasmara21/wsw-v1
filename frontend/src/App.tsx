import React from 'react'
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import Health from './components/Health'
import ScenarioForm from './components/ScenarioForm'
import AssetsPage from './pages/AssetsPage'
import DashboardPage from './pages/DashboardPage'

export default function App() {
  return (
    <BrowserRouter>
      <header style={{display:'flex', alignItems:'center', justifyContent:'space-between', padding:12, background:'#0b1226', color:'#fff'}}>
        <div style={{fontWeight:700, fontSize:18}}>WallStreetWar</div>
        <nav>
          <Link to="/" style={{color:'#fff', marginRight:12}}>Dashboard</Link>
          <Link to="/assets" style={{color:'#fff', marginRight:12}}>Assets</Link>
          <Link to="/scenarios" style={{color:'#fff'}}>Scenarios</Link>
        </nav>
      </header>
      <main style={{padding:20}}>
        <Routes>
          <Route path="/" element={<DashboardPage/>} />
          <Route path="/assets" element={<AssetsPage/>} />
          <Route path="/scenarios" element={<div><h2>Scenarios</h2><ScenarioForm/></div>} />
        </Routes>
      </main>
    </BrowserRouter>
  )
 }
