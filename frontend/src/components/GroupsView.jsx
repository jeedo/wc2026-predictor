import { useFetch } from '../hooks/useFetch'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

function TeamList({ teams }) {
  return (
    <ul className="team-list">
      {teams.map(t => <li key={t.teamId ?? t.name}>{t.name}</li>)}
    </ul>
  )
}

function MatchPredictions({ matches }) {
  if (!matches?.length) return null
  return (
    <div className="match-predictions">
      <h3 className="match-predictions-title">Match Predictions</h3>
      {matches.map((m, i) => (
        <div key={i} className="match-prediction-row">
          <span className="mp-team home">{m.homeTeam}</span>
          <span className="mp-score">{m.predictedHomeScore} – {m.predictedAwayScore}</span>
          <span className="mp-team away">{m.awayTeam}</span>
          <span className="mp-md">MD{m.matchday}</span>
        </div>
      ))}
    </div>
  )
}

function GroupCard({ group, teams = [], prediction }) {
  return (
    <div className="group-card">
      <h2 className="group-title">Group {group}</h2>

      {prediction ? (
        <div className="group-prediction">
          <div className="prediction-row winner">
            <span className="badge">1st</span>
            <span className="team-name">{prediction.winner}</span>
          </div>
          <div className="prediction-row runner-up">
            <span className="badge">2nd</span>
            <span className="team-name">{prediction.runnerUp}</span>
          </div>
          {prediction.reasoning && (
            <p className="reasoning">{prediction.reasoning}</p>
          )}
          <MatchPredictions matches={prediction.matches} />
        </div>
      ) : (
        <TeamList teams={teams} />
      )}
    </div>
  )
}

export default function GroupsView() {
  const groups = useFetch(`${API_BASE}/api/groups`)
  const predictions = useFetch(`${API_BASE}/api/predictions`)

  if (groups.loading) return <p className="status">Loading groups…</p>
  if (groups.error) return <p className="status error">Error: {groups.error}</p>
  if (!groups.data?.groups?.length) return <p className="status">No group data yet.</p>

  // Build a prediction lookup by group letter (null if no predictions yet)
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
          />
        ))}
      </div>
    </section>
  )
}
