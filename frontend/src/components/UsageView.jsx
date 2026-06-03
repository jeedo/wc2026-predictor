import { useFetch } from '../hooks/useFetch'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

function UsageBar({ percent }) {
  const clamped = Math.min(percent ?? 0, 100)
  const color = clamped >= 90 ? 'var(--red, #e53e3e)' : clamped >= 70 ? 'var(--orange, #dd6b20)' : 'var(--green, #38a169)'
  return (
    <div className="usage-bar-track" role="progressbar" aria-valuenow={clamped} aria-valuemin={0} aria-valuemax={100}>
      <div className="usage-bar-fill" style={{ width: `${clamped}%`, backgroundColor: color }} />
    </div>
  )
}

function ProviderCard({ provider }) {
  const { name, callCount, limit, window: win, percentUsed, inputTokens, outputTokens } = provider
  return (
    <div className="provider-card">
      <h2 className="provider-name">{name}</h2>
      <div className="provider-stat">
        <span className="stat-label">Calls today</span>
        <span className="stat-value">
          {limit != null ? `${callCount} / ${limit}` : callCount}
        </span>
      </div>
      {limit != null && (
        <>
          <UsageBar percent={percentUsed} />
          <p className="usage-window">{percentUsed}% of {win}ly limit</p>
        </>
      )}
      {inputTokens != null && (
        <div className="provider-stat">
          <span className="stat-label">Tokens today</span>
          <span className="stat-value">{(inputTokens + (outputTokens ?? 0)).toLocaleString()} ({inputTokens.toLocaleString()} in / {(outputTokens ?? 0).toLocaleString()} out)</span>
        </div>
      )}
    </div>
  )
}

export default function UsageView() {
  const { data, loading, error } = useFetch(`${API_BASE}/api/usage`)

  if (loading) return <p className="status">Loading…</p>
  if (error) return <p className="status error">Error: {error}</p>
  if (!data?.providers?.length) return <p className="status">No usage data yet.</p>

  return (
    <section className="usage-view">
      <h1>API Usage</h1>
      {data.asOf && (
        <p className="meta">As of {new Date(data.asOf).toLocaleString()}</p>
      )}
      <div className="provider-grid">
        {data.providers.map(p => <ProviderCard key={p.name} provider={p} />)}
      </div>
    </section>
  )
}
