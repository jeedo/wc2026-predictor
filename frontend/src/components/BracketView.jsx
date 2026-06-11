import { useMemo } from 'react'
import { useFetch } from '../hooks/useFetch'
import { getFlag } from '../utils/teamFlags'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

const KNOCKOUT_STAGES = [
  { key: 'LAST_32',       label: 'Round of 32' },
  { key: 'LAST_16',       label: 'Round of 16' },
  { key: 'QUARTER_FINALS', label: 'Quarter-Finals' },
  { key: 'SEMI_FINALS',   label: 'Semi-Finals' },
  { key: 'THIRD_PLACE',   label: 'Third Place' },
  { key: 'FINAL',         label: 'Final' },
]

function MatchCard({ homeTeam, awayTeam, predictedWinner, predictedHomeScore, predictedAwayScore, confidence }) {
  const hasPred = predictedWinner != null
  return (
    <div className="bracket-match">
      <div className={`bracket-team ${predictedWinner === homeTeam ? 'winner' : ''}`}>
        <span className="bracket-team-name">{getFlag(homeTeam)} {homeTeam ?? 'TBD'}</span>
        {hasPred && <span className="bracket-team-score">{predictedHomeScore}</span>}
      </div>
      <div className={`bracket-team ${predictedWinner === awayTeam ? 'winner' : ''}`}>
        <span className="bracket-team-name">{getFlag(awayTeam)} {awayTeam ?? 'TBD'}</span>
        {hasPred && <span className="bracket-team-score">{predictedAwayScore}</span>}
      </div>
      {hasPred && confidence && (
        <span className={`bracket-confidence confidence-badge ${confidence}`}>{confidence}</span>
      )}
    </div>
  )
}

export default function BracketView() {
  const { data, loading, error } = useFetch(`${API_BASE}/api/predictions`)

  const knockoutByStage = useMemo(() => {
    const map = {}
    data?.knockout?.forEach(s => { map[s.stage] = s.matches })
    return map
  }, [data])

  if (loading) return (
    <phantom-ui loading="" count="4" count-gap="0.6rem">
      <div className="bracket-match" style={{ minHeight: '80px' }} />
    </phantom-ui>
  )
  if (error) return <p className="status error">Error: {error}</p>

  const hasKnockout = data?.knockout?.length > 0

  return (
    <section className="bracket-view">
      <h1>Knockout Bracket</h1>
      {!hasKnockout ? (
        <p className="status meta">
          Bracket predictions will appear here once the group stage concludes (~June 25).
        </p>
      ) : (
        <div className="bracket-layout">
          {KNOCKOUT_STAGES.map(stage => {
            const matches = knockoutByStage[stage.key]
            if (!matches?.length) return null
            return (
              <div key={stage.key} className="bracket-round">
                <div className="bracket-round-label">{stage.label}</div>
                <div className="bracket-matches">
                  {matches.map((m, i) => (
                    <MatchCard key={m.fixtureId ?? i} {...m} />
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}
