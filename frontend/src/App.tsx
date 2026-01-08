import React from 'react'
import Health from './components/Health'
import Assets from './components/Assets'
import ScenarioForm from './components/ScenarioForm'

export default function App() {
  return (
    <div className="app">
      <header>
        <h1>WallStreetWar — Frontend MVP</h1>
      </header>

      <main>
        <section className="card">
          <h2>System Health</h2>
          <Health />
        </section>

        <section className="card">
          <h2>Assets</h2>
          <Assets />
        </section>

        <section className="card">
          <h2>Run Scenario</h2>
          <ScenarioForm />
        </section>
      </main>

      <footer>
        <small>Minimal frontend — uses Vite proxy to call backend</small>
      </footer>
    </div>
  )
}
