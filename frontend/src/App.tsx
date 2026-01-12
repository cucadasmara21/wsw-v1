import React from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { OverviewPage } from './pages/OverviewPage'
import { UniversePage } from './pages/UniversePage'
import { AssetDetailPage } from './pages/AssetDetailPage'
import Health from './components/Health'
import { MetricsPage } from './pages/MetricsPage'
import { AlertsPage } from './pages/AlertsPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<OverviewPage />} />
          <Route path="universe" element={<UniversePage />} />
          <Route path="assets/:id" element={<AssetDetailPage />} />
          <Route path="health" element={<Health />} />
          <Route path="metrics" element={<MetricsPage />} />
          <Route path="alerts" element={<AlertsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
