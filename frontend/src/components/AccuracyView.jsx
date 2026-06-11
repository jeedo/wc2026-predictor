import { useFetch } from '../hooks/useFetch'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

function KnockoutAccuracySection({ knockout }) {
  if (!knockout || knockout.total === 0) return null
  const pct = Math.round((knockout.score / knockout.total) * 100)
  return (
    <div className="knockout-accuracy">
      <h2>Knockout Stage</h2>
      <div className="score-header">
        <div className="score-display">
          <span className="score-value">{knockout.score} / {knockout.total}</span>
          <span className="score-label">knockout matches predicted correctly</span>
        </div>
        <div className="score-bar">
          <div className="score-fill" style={{ width: `${pct}%` }} />
        </div>
      </div>
    </div>
  )
}

function ScoreHeader({ score, totalGroups, matchday }) {
  const pct = Math.round((score / totalGroups) * 100)
  return (
    <div className="score-header">
      <div className="score-display">
        <span className="score-value">{score} / {totalGroups}</span>
        <span className="score-label">groups correct after Matchday {matchday}</span>
      </div>
      <div className="score-bar">
        <div className="score-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function GroupRow({ group, correct, predictedWinner, actualWinner, predictedRunnerUp, actualRunnerUp }) {
  return (
    <tr role="row" className={correct ? 'correct' : 'incorrect'}>
      <td className="group-label">Group {group}</td>
      <td className="predicted">
        <span>{predictedWinner}</span>
        <span className="separator">/</span>
        <span>{predictedRunnerUp}</span>
      </td>
      <td className="actual">
        <span>{actualWinner}</span>
        <span className="separator">/</span>
        <span>{actualRunnerUp}</span>
      </td>
      <td className="result-icon">{correct ? '✓' : '✗'}</td>
    </tr>
  )
}

export default function AccuracyView() {
  const { data, loading, error } = useFetch(`${API_BASE}/api/accuracy`)

  if (loading) return (
    <phantom-ui loading="" count="12" count-gap="0.15rem">
      <div style={{ height: '40px', background: 'var(--surface)', borderRadius: '4px' }} />
    </phantom-ui>
  )
  if (error) {
    if (error.includes('404') || error.includes('HTTP 404')) {
      return <p className="status">No accuracy data yet — check back after Matchday 1.</p>
    }
    return <p className="status error">Error: {error}</p>
  }
  if (!data) return <p className="status">No accuracy data yet — check back after Matchday 1.</p>

  return (
    <section className="accuracy-view">
      <h1>Prediction Accuracy</h1>
      <h2>Group Stage</h2>
      <ScoreHeader score={data.score} totalGroups={data.totalGroups} matchday={data.matchday} />
      <table className="accuracy-table">
        <thead>
          <tr role="row">
            <th>Group</th>
            <th>Predicted (1st / 2nd)</th>
            <th>Actual (1st / 2nd)</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {data.groups.map(g => <GroupRow key={g.group} {...g} />)}
        </tbody>
      </table>
      <KnockoutAccuracySection knockout={data.knockout} />
    </section>
  )
}
