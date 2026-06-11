import { render, screen, waitFor } from '@testing-library/react'
import { vi } from 'vitest'
import GroupsView from '../components/GroupsView'

const GROUPS_DATA = {
  groups: [
    { group: 'A', teams: [{ teamId: 1, name: 'Germany' }, { teamId: 2, name: 'Mexico' }] },
    { group: 'B', teams: [{ teamId: 3, name: 'Brazil' }, { teamId: 4, name: 'Argentina' }] },
  ],
}

const PREDICTIONS = {
  matchday: 1,
  generatedAt: '2026-06-12T10:00:00Z',
  groups: [
    { group: 'A', winner: 'Germany', runnerUp: 'Mexico', confidence: 'high', reasoning: 'Strong FIFA ranking.' },
    { group: 'B', winner: 'Brazil', runnerUp: 'Argentina', confidence: 'medium', reasoning: 'Brazil leads.' },
  ],
}

const PREDICTIONS_WITH_MATCHES = {
  matchday: 1,
  generatedAt: '2026-06-12T10:00:00Z',
  groups: [
    {
      group: 'A',
      winner: 'Germany',
      runnerUp: 'Mexico',
      confidence: 'high',
      reasoning: 'Strong FIFA ranking.',
      matches: [
        { homeTeam: 'Germany', awayTeam: 'Mexico', matchday: 1, predictedHomeScore: 2, predictedAwayScore: 1, confidence: 'high' },
        { homeTeam: 'Germany', awayTeam: 'Poland', matchday: 2, predictedHomeScore: 1, predictedAwayScore: 0, confidence: 'medium' },
      ],
    },
  ],
}

const NOT_FOUND = { ok: false, status: 404, json: () => Promise.resolve({ error: 'Not found' }) }

afterEach(() => vi.restoreAllMocks())

test('shows group teams when no predictions available', async () => {
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(GROUPS_DATA) })
    .mockResolvedValueOnce(NOT_FOUND))
  render(<GroupsView />)
  await waitFor(() => {
    expect(screen.getByText('Group A')).toBeInTheDocument()
    expect(screen.getByText(/Germany/)).toBeInTheDocument()
  })
})

test('shows predicted winner and runner-up when predictions exist', async () => {
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(GROUPS_DATA) })
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(PREDICTIONS) }))
  render(<GroupsView />)
  await waitFor(() => {
    expect(screen.getByText(/Germany/)).toBeInTheDocument()
    expect(screen.getByText(/Mexico/)).toBeInTheDocument()
    expect(screen.getByText(/Strong FIFA ranking/)).toBeInTheDocument()
  })
})

test('shows confidence badge next to winner', async () => {
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(GROUPS_DATA) })
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(PREDICTIONS) }))
  render(<GroupsView />)
  await waitFor(() => {
    // Confidence badges should appear in uppercase
    const badges = screen.getAllByText(/high|medium|low/i)
    expect(badges.length).toBeGreaterThan(0)
  })
})

test('shows loading state initially', () => {
  vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})))
  render(<GroupsView />)
  expect(document.querySelectorAll('.group-card--skeleton').length).toBe(12)
})

test('shows error when groups fetch fails', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')))
  render(<GroupsView />)
  await waitFor(() => expect(screen.getByText(/error/i)).toBeInTheDocument())
})

test('shows individual match predictions when matches are present', async () => {
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(GROUPS_DATA) })
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(PREDICTIONS_WITH_MATCHES) }))
  render(<GroupsView />)
  await waitFor(() => {
    // Score display for a predicted match
    expect(screen.getByText(/2\s*[–-]\s*1/)).toBeInTheDocument()
    // Match heading
    expect(screen.getByText(/match predictions/i)).toBeInTheDocument()
  })
})

test('shows no match predictions section when matches array is absent', async () => {
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(GROUPS_DATA) })
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(PREDICTIONS) }))
  render(<GroupsView />)
  await waitFor(() => {
    expect(screen.getByText(/Germany/)).toBeInTheDocument()
    // No score dashes when there are no match predictions
    expect(screen.queryByText(/\d\s*[–-]\s*\d/)).not.toBeInTheDocument()
  })
})
