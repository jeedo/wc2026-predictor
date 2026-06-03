import { useState } from 'react'
import { useFetch } from '../hooks/useFetch'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const MATCHDAYS = [1, 2, 3]

function FixtureRow({
  homeTeam,
  awayTeam,
  homeScore,
  awayScore,
  status,
  kickoff,
  predictedHomeScore,
  predictedAwayScore,
}) {
  const finished = status === 'FT'
  const live = ['1H', '2H', 'HT', 'ET', 'P'].includes(status)
  const upcoming = status === 'NS'
  const kickoffDate = new Date(kickoff)
  const timeStr = kickoffDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  const dateStr = kickoffDate.toLocaleDateString([], { month: 'short', day: 'numeric' })

  const hasPrediction =
    predictedHomeScore != null && predictedAwayScore != null

  return (
    <div className={`fixture-row ${status.toLowerCase()}`}>
      <span className="team home">{homeTeam}</span>
      <span className="score">
        {finished || live ? (
          `${homeScore} – ${awayScore}`
        ) : upcoming && hasPrediction ? (
          <div>
            <div className="predicted-score">
              {predictedHomeScore} – {predictedAwayScore} <span className="pred-label">(pred)</span>
            </div>
            <div className="kickoff-time">{dateStr} {timeStr}</div>
          </div>
        ) : (
          <span className="kickoff">{dateStr} {timeStr}</span>
        )}
      </span>
      <span className="team away">{awayTeam}</span>
      <span className={`status-badge ${live ? 'live' : ''}`}>
        {finished ? 'FT' : live ? status : 'Upcoming'}
      </span>
    </div>
  )
}

function MatchdayFixtures({ matchday }) {
  const { data, loading, error } = useFetch(`${API_BASE}/api/fixtures/${matchday}`)

  if (loading) return <p className="status">Loading…</p>
  if (error) return <p className="status error">Error: {error}</p>
  if (!data?.fixtures?.length) return <p className="status">No fixtures for Matchday {matchday}.</p>

  return (
    <div className="fixtures-list">
      {data.fixtures.map(f => <FixtureRow key={f.id} {...f} />)}
    </div>
  )
}

export default function FixturesView() {
  const [matchday, setMatchday] = useState(1)

  return (
    <section className="fixtures-view">
      <h1>Fixtures</h1>
      <div className="matchday-tabs" role="tablist">
        {MATCHDAYS.map(md => (
          <button
            key={md}
            role="tab"
            aria-selected={matchday === md}
            className={`tab-btn ${matchday === md ? 'active' : ''}`}
            onClick={() => setMatchday(md)}
          >
            Matchday {md}
          </button>
        ))}
      </div>
      <MatchdayFixtures matchday={matchday} />
    </section>
  )
}
