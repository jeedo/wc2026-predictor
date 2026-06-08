import { useFetch } from '../hooks/useFetch'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

const FLAGS = {
  'Algeria': '🇩🇿', 'Argentina': '🇦🇷', 'Australia': '🇦🇺', 'Austria': '🇦🇹',
  'Belgium': '🇧🇪', 'Bosnia-Herzegovina': '🇧🇦', 'Bosnia and Herzegovina': '🇧🇦',
  'Brazil': '🇧🇷', 'Canada': '🇨🇦', 'Cape Verde': '🇨🇻', 'Cape Verde Islands': '🇨🇻',
  'Colombia': '🇨🇴', 'Congo DR': '🇨🇩', 'DR Congo': '🇨🇩', 'Croatia': '🇭🇷',
  'Curaçao': '🇨🇼', 'Curacao': '🇨🇼', 'Czechia': '🇨🇿', 'Czech Republic': '🇨🇿',
  'Ecuador': '🇪🇨', 'Egypt': '🇪🇬', 'England': '🏴󠁧󠁢󠁥󠁮󠁧󠁿', 'France': '🇫🇷',
  'Germany': '🇩🇪', 'Ghana': '🇬🇭', 'Haiti': '🇭🇹', 'Iran': '🇮🇷',
  'Iraq': '🇮🇶', 'Ivory Coast': '🇨🇮', "Côte d'Ivoire": '🇨🇮', 'Japan': '🇯🇵',
  'Jordan': '🇯🇴', 'Mexico': '🇲🇽', 'Morocco': '🇲🇦', 'Netherlands': '🇳🇱',
  'New Zealand': '🇳🇿', 'Norway': '🇳🇴', 'Panama': '🇵🇦', 'Paraguay': '🇵🇾',
  'Portugal': '🇵🇹', 'Qatar': '🇶🇦', 'Saudi Arabia': '🇸🇦', 'Scotland': '🏴󠁧󠁢󠁳󠁣󠁴󠁿',
  'Senegal': '🇸🇳', 'South Africa': '🇿🇦', 'South Korea': '🇰🇷', 'Spain': '🇪🇸',
  'Sweden': '🇸🇪', 'Switzerland': '🇨🇭', 'Tunisia': '🇹🇳', 'Turkey': '🇹🇷',
  'Türkiye': '🇹🇷', 'United States': '🇺🇸', 'Uruguay': '🇺🇾', 'Uzbekistan': '🇺🇿',
}

function getFlag(name) {
  return FLAGS[name] ?? ''
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

function GroupCard({ group, teams = [], prediction }) {
  return (
    <div className="group-card">
      <h2 className="group-title">Group {group}</h2>

      {prediction ? (
        <div className="group-prediction">
          <div className="prediction-row winner">
            <span className="badge">1st</span>
            <span className="team-name">{getFlag(prediction.winner)} {prediction.winner}</span>
            {prediction.confidence && (
              <span className={`confidence-badge ${prediction.confidence}`}>
                {prediction.confidence}
              </span>
            )}
          </div>
          <div className="prediction-row runner-up">
            <span className="badge">2nd</span>
            <span className="team-name">{getFlag(prediction.runnerUp)} {prediction.runnerUp}</span>
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
            </li>
          ))}
        </ul>
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
