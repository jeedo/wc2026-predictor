import { useFetch } from '../hooks/useFetch'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

function GroupCard({ group, winner, runnerUp, reasoning }) {
  return (
    <div className="group-card">
      <h2 className="group-title">Group {group}</h2>
      <div className="group-prediction">
        <div className="prediction-row winner">
          <span className="badge">1st</span>
          <span className="team-name">{winner}</span>
        </div>
        <div className="prediction-row runner-up">
          <span className="badge">2nd</span>
          <span className="team-name">{runnerUp}</span>
        </div>
      </div>
      {reasoning && <p className="reasoning">{reasoning}</p>}
    </div>
  )
}

export default function GroupsView() {
  const { data, loading, error } = useFetch(`${API_BASE}/api/predictions`)

  if (loading) return <p className="status">Loading predictions…</p>
  if (error) return <p className="status error">Error: {error}</p>
  if (!data?.groups?.length) return <p className="status">No predictions yet.</p>

  return (
    <section className="groups-view">
      <h1>Group Stage Predictions</h1>
      <p className="meta">Generated after Matchday {data.matchday}</p>
      <div className="group-grid">
        {data.groups.map(g => (
          <GroupCard key={g.group} {...g} />
        ))}
      </div>
    </section>
  )
}
