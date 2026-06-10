import { useState, useEffect } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export default function TeamNewsModal({ teamName, onClose }) {
  const [loading, setLoading] = useState(true)
  const [snippets, setSnippets] = useState([])
  const [date, setDate] = useState(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    fetch(`${API_BASE}/api/news/${encodeURIComponent(teamName)}`)
      .then(r => r.json())
      .then(data => {
        setSnippets(data.snippets ?? [])
        setDate(data.date ?? null)
        setLoading(false)
      })
      .catch(() => {
        setError(true)
        setLoading(false)
      })
  }, [teamName])

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div role="dialog" aria-modal="true" className="news-modal-backdrop" onClick={onClose}>
      <div className="news-modal-box" onClick={e => e.stopPropagation()}>
        <div className="news-modal-header">
          <h2>{teamName}</h2>
          <button aria-label="Close" onClick={onClose}>✕</button>
        </div>
        {loading && <p>Loading…</p>}
        {error && <p>Could not load news.</p>}
        {!loading && !error && snippets.length === 0 && (
          <p>No recent news available.</p>
        )}
        {!loading && !error && snippets.length > 0 && (
          <>
            {date && <p className="news-date">{date}</p>}
            <ul className="news-snippets">
              {snippets.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </>
        )}
      </div>
    </div>
  )
}
