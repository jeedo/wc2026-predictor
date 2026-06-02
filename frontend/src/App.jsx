import { useState } from 'react'
import GroupsView from './components/GroupsView'
import FixturesView from './components/FixturesView'
import AccuracyView from './components/AccuracyView'
import './App.css'

const VIEWS = [
  { id: 'groups', label: 'Groups' },
  { id: 'fixtures', label: 'Fixtures' },
  { id: 'accuracy', label: 'Accuracy' },
]

export default function App() {
  const [view, setView] = useState('groups')

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-inner">
          <span className="app-logo">⚽ WC2026 Predictor</span>
          <nav className="app-nav" aria-label="Main navigation">
            {VIEWS.map(v => (
              <button
                key={v.id}
                className={`nav-btn ${view === v.id ? 'active' : ''}`}
                onClick={() => setView(v.id)}
                aria-current={view === v.id ? 'page' : undefined}
              >
                {v.label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      <main className="app-main">
        {view === 'groups' && <GroupsView />}
        {view === 'fixtures' && <FixturesView />}
        {view === 'accuracy' && <AccuracyView />}
      </main>

      <footer className="app-footer">
        Powered by Claude Haiku · API-Football · Azure
      </footer>
    </div>
  )
}
