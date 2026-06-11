import { useState, useMemo } from 'react'
import { useFetch } from '../hooks/useFetch'
import { getFlag } from '../utils/teamFlags'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const MATCHDAYS = [1, 2, 3]

const KNOCKOUT_STAGES = [
  { key: 'LAST_32',        label: 'Round of 32' },
  { key: 'LAST_16',        label: 'Round of 16' },
  { key: 'QUARTER_FINALS', label: 'Quarter-Finals' },
  { key: 'SEMI_FINALS',    label: 'Semi-Finals' },
  { key: 'THIRD_PLACE',    label: 'Third Place' },
  { key: 'FINAL',          label: 'Final' },
]

function FixtureRow({
  homeTeam,
  awayTeam,
  homeScore,
  awayScore,
  status,
  kickoff,
  predictedHomeScore,
  predictedAwayScore,
  predictedConfidence,
}) {
  const finished = status === 'FT'
  const live = ['1H', '2H', 'HT', 'ET', 'P'].includes(status)
  const upcoming = status === 'NS'
  const kickoffDate = new Date(kickoff)
  const timeStr = kickoffDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  const dateStr = kickoffDate.toLocaleDateString([], { month: 'short', day: 'numeric' })

  const hasPrediction = predictedHomeScore != null && predictedAwayScore != null

  return (
    <div className={`fixture-row ${status.toLowerCase()}`}>
      <span className="team home">
        {getFlag(homeTeam) && <span className="team-flag">{getFlag(homeTeam)}</span>}
        <span className="team-name-text">{homeTeam ?? 'TBD'}</span>
      </span>
      <div className="score">
        {finished || live ? (
          `${homeScore} – ${awayScore}`
        ) : upcoming && hasPrediction ? (
          <div>
            <div className="predicted-score">
              <span className="pred-score-line">{predictedHomeScore} – {predictedAwayScore}</span>
              <span className={`pred-label ${predictedConfidence || ''}`}>
                {predictedConfidence ? `pred · ${predictedConfidence}` : 'pred'}
              </span>
            </div>
            <div className="kickoff-time">{dateStr} {timeStr}</div>
          </div>
        ) : (
          <span className="kickoff">{dateStr} {timeStr}</span>
        )}
      </div>
      <span className="team away">
        {getFlag(awayTeam) && <span className="team-flag">{getFlag(awayTeam)}</span>}
        <span className="team-name-text">{awayTeam ?? 'TBD'}</span>
      </span>
      <span className={`status-badge ${live ? 'live' : ''}`}>
        {finished ? 'FT' : live ? status : 'Upcoming'}
      </span>
    </div>
  )
}

function MatchdayFixtures({ matchday }) {
  const { data, loading, error } = useFetch(`${API_BASE}/api/fixtures/${matchday}`)

  if (loading) return (
    <div className="fixtures-list">
      <phantom-ui loading={true} count={8} count-gap={8}>
        <div className="fixture-row">
          <span className="team home">
            <span className="team-flag">🏳️</span>
            <span className="team-name-text">Team Name</span>
          </span>
          <div className="score">1 – 0</div>
          <span className="team away">
            <span className="team-flag">🏳️</span>
            <span className="team-name-text">Team Name</span>
          </span>
          <span className="status-badge">FT</span>
        </div>
      </phantom-ui>
    </div>
  )
  if (error) return <p className="status error">Error: {error}</p>
  if (!data?.fixtures?.length) return <p className="status">No fixtures for Matchday {matchday}.</p>

  return (
    <div className="fixtures-list">
      {data.fixtures.map(f => <FixtureRow key={f.id} {...f} />)}
    </div>
  )
}

function KnockoutStageSection({ stage, predsByFixtureId }) {
  const { data, loading, error } = useFetch(`${API_BASE}/api/fixtures/stage/${stage.key}`)

  if (loading) return <p className="status">Loading {stage.label}…</p>
  if (error || !data?.fixtures?.length) return null

  return (
    <div className="knockout-stage-section">
      <h3 className="round-label">{stage.label}</h3>
      <div className="fixtures-list">
        {data.fixtures.map(f => {
          const pred = predsByFixtureId[f.fixtureId]
          return (
            <FixtureRow
              key={f.id}
              {...f}
              predictedHomeScore={pred?.predictedHomeScore}
              predictedAwayScore={pred?.predictedAwayScore}
              predictedConfidence={pred?.confidence}
            />
          )
        })}
      </div>
    </div>
  )
}

function KnockoutFixtures() {
  const { data: predData, loading: predLoading } = useFetch(`${API_BASE}/api/predictions`)

  const predsByFixtureId = useMemo(() => {
    const map = {}
    predData?.knockout?.forEach(stagePred => {
      stagePred.matches.forEach(m => { map[m.fixtureId] = m })
    })
    return map
  }, [predData])

  if (predLoading) return (
    <div className="fixtures-list">
      <phantom-ui loading="" count="4" count-gap="0.5rem">
        <div className="fixture-row">
          <span className="team home">
            <span className="team-flag">🏳️</span>
            <span className="team-name-text">Team Name</span>
          </span>
          <div className="score">1 – 0</div>
          <span className="team away">
            <span className="team-flag">🏳️</span>
            <span className="team-name-text">Team Name</span>
          </span>
          <span className="status-badge">FT</span>
        </div>
      </phantom-ui>
    </div>
  )

  if (predData && !predData.knockout?.length) {
    return (
      <p className="status">
        Knockout fixtures will appear here once the group stage concludes (~June 25).
      </p>
    )
  }

  return (
    <div className="knockout-fixtures">
      {KNOCKOUT_STAGES.map(stage => (
        <KnockoutStageSection key={stage.key} stage={stage} predsByFixtureId={predsByFixtureId} />
      ))}
    </div>
  )
}

export default function FixturesView() {
  const [tab, setTab] = useState(1)

  return (
    <section className="fixtures-view">
      <h1>Fixtures</h1>
      <div className="matchday-tabs" role="tablist">
        {MATCHDAYS.map(md => (
          <button
            key={md}
            role="tab"
            aria-selected={tab === md}
            className={`tab-btn ${tab === md ? 'active' : ''}`}
            onClick={() => setTab(md)}
          >
            Matchday {md}
          </button>
        ))}
        <button
          role="tab"
          aria-selected={tab === 'knockout'}
          className={`tab-btn ${tab === 'knockout' ? 'active' : ''}`}
          onClick={() => setTab('knockout')}
        >
          Knockout
        </button>
      </div>
      {tab === 'knockout' ? (
        <KnockoutFixtures />
      ) : (
        <MatchdayFixtures matchday={tab} />
      )}
    </section>
  )
}
