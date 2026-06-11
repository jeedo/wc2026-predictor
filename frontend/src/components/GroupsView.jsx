import { useState } from 'react'
import { useFetch } from '../hooks/useFetch'
import TeamNewsModal from './TeamNewsModal'
import { getFlag } from '../utils/teamFlags'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

function NewsButton({ team, onClick }) {
  return (
    <button
      className="news-icon-btn"
      title={`News: ${team}`}
      aria-label={`News for ${team}`}
      onClick={() => onClick(team)}
    >
      📰
    </button>
  )
}

function MatchPredictions({ matches }) {
  if (!matches?.length) return null
  return (
    <div className="match-predictions">
      <h3 className="match-predictions-title">Match Predictions</h3>
      {matches.map((m, i) => {
        const homeWins = m.predictedHomeScore > m.predictedAwayScore
        const awayWins = m.predictedAwayScore > m.predictedHomeScore
        return (
          <div key={i} className="mp-row">
            <span className="mp-md-badge">🗓 {m.matchday}</span>
            <div className="mp-fixture">
              <span className={`mp-team mp-home${homeWins ? ' mp-winner' : ''}`}>
                {getFlag(m.homeTeam)} {m.homeTeam}
              </span>
              <span className="mp-score">{m.predictedHomeScore} – {m.predictedAwayScore}</span>
              <span className={`mp-team mp-away${awayWins ? ' mp-winner' : ''}`}>
                {m.awayTeam} {getFlag(m.awayTeam)}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function GroupCard({ group, teams = [], prediction, onNewsClick }) {
  return (
    <div className="group-card">
      <h2 className="group-title">Group {group}</h2>

      {prediction ? (
        <div className="group-prediction">
          <div className="prediction-row winner">
            <span className="badge">1st</span>
            <span className="team-name">{getFlag(prediction.winner)} {prediction.winner}</span>
            <NewsButton team={prediction.winner} onClick={onNewsClick} />
            {prediction.confidence && (
              <span className={`confidence-badge ${prediction.confidence}`}>
                {prediction.confidence}
              </span>
            )}
          </div>
          <div className="prediction-row runner-up">
            <span className="badge">2nd</span>
            <span className="team-name">{getFlag(prediction.runnerUp)} {prediction.runnerUp}</span>
            <NewsButton team={prediction.runnerUp} onClick={onNewsClick} />
          </div>
          {prediction.reasoning && (
            <p className="reasoning">{prediction.reasoning}</p>
          )}
          <MatchPredictions matches={prediction.matches} />
        </div>
      ) : (
        <ul className="team-list">
          {teams.map(t => (
            <li key={t.teamId ?? t.name}>
              {getFlag(t.name)} {t.name}
              <NewsButton team={t.name} onClick={onNewsClick} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function GroupsView() {
  const [newsTeam, setNewsTeam] = useState(null)
  const groups = useFetch(`${API_BASE}/api/groups`)
  const predictions = useFetch(`${API_BASE}/api/predictions`)

  if (groups.loading || predictions.loading) return (
    <section className="groups-view">
      <h1>Group Stage</h1>
      <div className="group-grid">
        {Array.from({ length: 12 }).map((_, i) => (
          <div key={i} className="group-card group-card--skeleton" />
        ))}
      </div>
    </section>
  )
  if (groups.error) return <p className="status error">Error: {groups.error}</p>
  if (!groups.data?.groups?.length) return <p className="status">No group data yet.</p>

  const predByGroup = {}
  if (predictions.data?.groups) {
    for (const p of predictions.data.groups) predByGroup[p.group] = p
  }

  const hasPredictions = Object.keys(predByGroup).length > 0

  return (
    <section className="groups-view">
      <h1>Group Stage {hasPredictions ? 'Predictions' : 'Teams'}</h1>
      {hasPredictions
        ? <p className="meta">AI predictions after Matchday {predictions.data.matchday}</p>
        : <p className="meta">Predictions will appear after Matchday 1 results</p>
      }
      <div className="group-grid">
        {groups.data.groups.map(({ group, teams }) => (
          <GroupCard
            key={group}
            group={group}
            teams={teams}
            prediction={predByGroup[group] ?? null}
            onNewsClick={setNewsTeam}
          />
        ))}
      </div>
      {newsTeam && (
        <TeamNewsModal teamName={newsTeam} onClose={() => setNewsTeam(null)} />
      )}
    </section>
  )
}
