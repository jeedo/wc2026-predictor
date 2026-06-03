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
    { group: 'A', winner: 'Germany', runnerUp: 'Mexico', reasoning: 'Strong FIFA ranking.' },
    { group: 'B', winner: 'Brazil', runnerUp: 'Argentina', reasoning: 'Brazil leads.' },
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
    expect(screen.getByText('Germany')).toBeInTheDocument()
  })
})

test('shows predicted winner and runner-up when predictions exist', async () => {
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(GROUPS_DATA) })
    .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(PREDICTIONS) }))
  render(<GroupsView />)
  await waitFor(() => {
    expect(screen.getByText('Germany')).toBeInTheDocument()
    expect(screen.getByText('Mexico')).toBeInTheDocument()
    expect(screen.getByText(/Strong FIFA ranking/)).toBeInTheDocument()
  })
})

test('shows loading state initially', () => {
  vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})))
  render(<GroupsView />)
  expect(screen.getByText(/loading/i)).toBeInTheDocument()
})

test('shows error when groups fetch fails', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network error')))
  render(<GroupsView />)
  await waitFor(() => expect(screen.getByText(/error/i)).toBeInTheDocument())
})
