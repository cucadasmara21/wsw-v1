import React from 'react'
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import Health from './components/Health'
import ScenarioForm from './components/ScenarioForm'
import AssetsPage from './pages/AssetsPage'

export default function App() {
  return (
    <BrowserRouter>
      <nav style={{padding:10, background:'#f3f3f3'}}>
        <Link to="/">Status</Link> | <Link to="/assets">Assets</Link> | <Link to="/scenarios">Scenarios</Link>
      </nav>
      <div style={{padding:20}}>
        <Routes>
          <Route path="/" element={<div><h1>System</h1><Health/></div>} />
          <Route path="/assets" element={<AssetsPage/>} />
          <Route path="/scenarios" element={<div><h2>Scenarios</h2><ScenarioForm/></div>} />
        </Routes>
      </div>
    </BrowserRouter>
  )
}
